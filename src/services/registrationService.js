// Mock submission abstraction. Swap the body of submitRegistration with a real
// API call once the official registration endpoint is available.
export async function submitRegistration(data) {
  await new Promise((resolve) => setTimeout(resolve, 1400));
  return { ok: true, data };
}
