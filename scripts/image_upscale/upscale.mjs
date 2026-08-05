import sharp from 'sharp'

const width = Number.parseInt(process.argv[2] || '', 10)
const height = Number.parseInt(process.argv[3] || '', 10)

if (!Number.isInteger(width) || !Number.isInteger(height) || width <= 0 || height <= 0) {
  process.stderr.write('Invalid target size')
  process.exit(2)
}

const chunks = []
for await (const chunk of process.stdin) chunks.push(chunk)
const input = Buffer.concat(chunks)

try {
  sharp.cache(false)
  sharp.concurrency(1)
  const output = await sharp(input)
    .rotate()
    .resize(width, height, {
      fit: 'fill',
      kernel: sharp.kernel.lanczos3,
      withoutEnlargement: false,
    })
    .toBuffer()
  process.stdout.write(output)
} catch (error) {
  process.stderr.write(error instanceof Error ? error.message : String(error))
  process.exit(1)
}
