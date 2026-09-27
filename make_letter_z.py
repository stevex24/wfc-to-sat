from PIL import Image, ImageDraw

SIZE = 16
SCALE = 32
HI = SIZE * SCALE

WHITE = 255
BLACK = 0

# Draw a large clean geometric Z.
img = Image.new("L", (HI, HI), WHITE)
draw = ImageDraw.Draw(img)

# Effective stroke thickness: about 2 pixels in the final 16x16 image.
W = 2 * SCALE

# Top horizontal stroke.
draw.line(
    [(0, SCALE), (HI - 1, SCALE)],
    fill=BLACK,
    width=W
)

# Diagonal: upper right all the way to lower left.
draw.line(
    [(HI - 1, SCALE), (0, HI - 1 - SCALE)],
    fill=BLACK,
    width=W
)

# Bottom horizontal stroke.
draw.line(
    [(0, HI - 1 - SCALE), (HI - 1, HI - 1 - SCALE)],
    fill=BLACK,
    width=W
)

# Reduce to 16x16 using area averaging.
small = img.resize((SIZE, SIZE), Image.Resampling.LANCZOS)

# Convert back to STRICTLY binary black/white.
small = small.point(lambda p: 0 if p < 192 else 255, mode="1")

# Save as normal PNG.
small.convert("RGBA").save("examples/letter-z-corrected.png")

print("Created examples/letter-z-corrected.png")
