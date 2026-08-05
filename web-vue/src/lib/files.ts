export async function dataUrlToFile(dataUrl: string, filename: string, fallbackType = 'application/octet-stream') {
  const response = await fetch(dataUrl)
  const blob = await response.blob()
  return new File([blob], filename, { type: blob.type || fallbackType })
}
