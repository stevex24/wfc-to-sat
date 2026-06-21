class CnfBuilder:
    def __init__(self):
        self.next_var = 1
        self.var_map = {}
        self.name_map = {}
        self.clauses = []

    def var_for(self, x: int, y: int, pattern_id: int) -> int:
        key = (x, y, pattern_id)

        if key not in self.var_map:
            self.var_map[key] = self.next_var
            self.name_map[self.next_var] = key
            self.next_var += 1

        return self.var_map[key]

    def add_clause(self, clause):
        self.clauses.append(list(clause))

    @property
    def num_vars(self) -> int:
        return self.next_var - 1

    def dimacs(self) -> str:
        lines = [f"p cnf {self.num_vars} {len(self.clauses)}"]

        for clause in self.clauses:
            lines.append(" ".join(str(lit) for lit in clause) + " 0")

        return "\n".join(lines) + "\n"


def patterns_to_cnf(patterns, allowed, width: int, height: int) -> CnfBuilder:
    cnf = CnfBuilder()

    # Create variables:
    # variable (x, y, pattern_id) means:
    # pattern_id is placed at position (x, y).
    for y in range(height):
        for x in range(width):
            for pattern in patterns:
                cnf.var_for(x, y, pattern.id)

    # Exactly one pattern per output position.
    for y in range(height):
        for x in range(width):

            # At least one pattern.
            cnf.add_clause(
                cnf.var_for(x, y, pattern.id)
                for pattern in patterns
            )

            # At most one pattern.
            for i in range(len(patterns)):
                for j in range(i + 1, len(patterns)):
                    cnf.add_clause([
                        -cnf.var_for(x, y, patterns[i].id),
                        -cnf.var_for(x, y, patterns[j].id),
                    ])

    def add_overlap_clauses(direction, dx, dy):
        for y in range(height):
            for x in range(width):

                nx = x + dx
                ny = y + dy

                if nx < 0 or nx >= width or ny < 0 or ny >= height:
                    continue

                for p1 in patterns:
                    for p2 in patterns:

                        if p2.id not in allowed[direction][p1.id]:
                            cnf.add_clause([
                                -cnf.var_for(x, y, p1.id),
                                -cnf.var_for(nx, ny, p2.id),
                            ])

    add_overlap_clauses("right", 1, 0)
    add_overlap_clauses("down", 0, 1)

    return cnf
