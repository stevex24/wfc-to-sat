def overlaps_right(left, right):
    size = len(left.rows)

    for y in range(size):
        if left.rows[y][1:] != right.rows[y][:size - 1]:
            return False

    return True


def overlaps_down(top, bottom):
    size = len(top.rows)

    for y in range(1, size):
        if top.rows[y] != bottom.rows[y - 1]:
            return False

    return True


def build_compatibility(patterns):
    allowed = {
        "right": {},
        "down": {}
    }

    for p1 in patterns:

        allowed["right"][p1.id] = []
        allowed["down"][p1.id] = []

        for p2 in patterns:

            if overlaps_right(p1, p2):
                allowed["right"][p1.id].append(p2.id)

            if overlaps_down(p1, p2):
                allowed["down"][p1.id].append(p2.id)

    return allowed
