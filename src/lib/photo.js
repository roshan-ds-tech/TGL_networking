/* Profile photos: shrink in the browser before uploading.
 *
 * A phone photo is often 3-5 MB; uploading that on mobile data is slow and the
 * server re-encodes it to 512 px anyway. Scaling to 1024 px here first makes
 * the upload ~200 KB. The server still validates and re-encodes everything
 * (it is the authority), so this is purely a speed-up. */
export const PHOTO_TYPES = ['image/png', 'image/jpeg', 'image/webp'];
const MAX_INPUT_BYTES = 15 * 1024 * 1024;
const MAX_EDGE = 1024;

export function photoError(file) {
  if (!file) return 'Choose a photo.';
  if (!PHOTO_TYPES.includes(file.type)) return 'Please choose a PNG, JPG or WEBP image.';
  if (file.size > MAX_INPUT_BYTES) return 'That image is too large. Please choose one under 15 MB.';
  return '';
}

/** Returns a JPEG Blob no larger than MAX_EDGE on its longest side. Falls
 *  back to the original file if the browser can't decode it here (the server
 *  then decides). */
export async function shrinkPhoto(file) {
  try {
    const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' });
    const scale = Math.min(1, MAX_EDGE / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    canvas.getContext('2d').drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close?.();
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.9));
    return blob && blob.size < file.size ? blob : file;
  } catch {
    return file;
  }
}
