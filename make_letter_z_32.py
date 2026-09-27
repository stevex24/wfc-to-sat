from PIL import Image, ImageDraw

SIZE = 32
SCALE = 16
HI = SIZE * SCALE

WHITE = 255
BLACK = 0

img = Image.new("L", (HI, HI), WHITE)
draw = ImageDraw.Draw(img)

# 4-pixel stroke in the final 32x32 image.
W = 4 * SCALE

# Put stroke centers 2 pixels in from the borders
# so the full stroke reaches the outer edges cleanly.
TOP_Y = 2 * SCALE
BOTTOM_Y = (SIZE - 3) * SCALE

# Top bar
draw.line(
    [(0, TOP_Y), (HI - 1, TOP_Y)],
    fill=BLACK,
    width=W
)

# Diagonal, from upper-right to lower-left
draw.line(
    [(HI - 1, TOP_Y), (0, BOTTOM_Y)],
    fill=BLACK,
    width=W
)

# Bottom bar
draw.line(
    [(0, BOTTOM_Y), (HI - 1, BOTTOM_Y)],
    fill=BLACK,
    width=W
)

# Downsample to 32x32.
small = img.resize((SIZE, SIZE), Image.LANCZOS)

# Threshold back to strict black/white.
small = small.point(lambda p: 0 if p < 192 else 255)

small.convert("RGBA").save("examples/letter-z-32.png")

print("Created examples/letter-z-32.png")
