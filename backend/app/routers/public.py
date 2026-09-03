"""Public (unauthenticated) registration intake."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..models import Registration
from ..ratelimit import client_ip, enforce
from ..schemas import RegistrationCreate
from ..security import hash_ip
from ..storage import save_payment_proof

router = APIRouter(prefix="/api", tags=["public"])


@router.post("/registrations", status_code=status.HTTP_201_CREATED)
async def create_registration(
    request: Request,
    full_name: str = Form(..., alias="name"),
    business_name: str = Form(..., alias="business"),
    email: str = Form(...),
    phone: str = Form(...),
    category: str = Form(...),
    employees: str = Form(...),
    business_age: str = Form(..., alias="age"),
    city: str | None = Form(default=None),
    agreed_terms: bool = Form(..., alias="agree"),
    media_consent: bool = Form(..., alias="mediaConsent"),
    payment_proof: UploadFile = File(..., alias="paymentProof"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    ip = client_ip(request)
    enforce(
        f"register:{ip}",
        settings.register_max_per_hour,
        3600,
        "Too many registration attempts from this network. Please try again later.",
    )

    try:
        data = RegistrationCreate(
            full_name=full_name,
            business_name=business_name,
            email=email,
            phone=phone,
            category=category,
            employees=employees,
            business_age=business_age,
            city=city,
            agreed_terms=agreed_terms,
            media_consent=media_consent,
        )
    except ValidationError as exc:
        # Surface field-level messages the SPA can map back onto inputs.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[
                {"field": str(e["loc"][0]) if e["loc"] else "", "message": e["msg"]}
                for e in exc.errors()
            ],
        )

    filename, mime, size = await save_payment_proof(payment_proof)

    registration = Registration(
        full_name=data.full_name,
        business_name=data.business_name,
        email=str(data.email).lower(),
        phone=data.phone,
        category=data.category,
        employees=data.employees,
        business_age=data.business_age,
        city=data.city or None,
        proof_filename=filename,
        proof_mime=mime,
        proof_bytes=size,
        agreed_terms=data.agreed_terms,
        media_consent=data.media_consent,
        submitter_ip_hash=hash_ip(ip),
    )
    db.add(registration)
    await db.commit()

    # Deliberately minimal: no internal IDs or counts leak to the public site.
    return {"status": "received", "name": data.full_name}
