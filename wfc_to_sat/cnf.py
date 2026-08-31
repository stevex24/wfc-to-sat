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

    def new_aux_var(self) -> int:
        """Allocate an unnamed variable that is not a pattern placement."""
        variable = self.next_var
        self.next_var += 1
        return variable

    @property
    def num_vars(self) -> int:
        return self.next_var - 1

    def dimacs(self) -> str:
        lines = [f"p cnf {self.num_vars} {len(self.clauses)}"]

        for clause in self.clauses:
            lines.append(" ".join(str(lit) for lit in clause) + " 0")

        return "\n".join(lines) + "\n"


def patterns_to_cnf(
    patterns, allowed, width: int, height: int, *, adjacency_encoding="forbidden-pairs",
    exactly_one_encoding="pairwise", timing_hook=None,
) -> CnfBuilder:
    if adjacency_encoding not in {"forbidden-pairs", "support"}:
        raise ValueError("unknown adjacency encoding")
    if exactly_one_encoding not in {"pairwise", "sequential"}:
        raise ValueError("unknown exactly-one encoding")
    cnf = CnfBuilder()

    def timing(event, stage):
        if timing_hook is not None:
            timing_hook(event, stage, cnf)

    # Create variables:
    # variable (x, y, pattern_id) means:
    # pattern_id is placed at position (x, y).
    timing("start", "variables")
    for y in range(height):
        for x in range(width):
            for pattern in patterns:
                cnf.var_for(x, y, pattern.id)
    timing("end", "variables")

    # Exactly one pattern per output position.
    timing("start", "exactly_one")
    for y in range(height):
        for x in range(width):

            # At least one pattern.
            cnf.add_clause(
                cnf.var_for(x, y, pattern.id)
                for pattern in patterns
            )

            variables = [cnf.var_for(x, y, pattern.id) for pattern in patterns]
            if exactly_one_encoding == "pairwise":
                # At most one pattern (the original/default encoding).
                for i in range(len(variables)):
                    for j in range(i + 1, len(variables)):
                        cnf.add_clause([-variables[i], -variables[j]])
            else:
                _add_sequential_at_most_one(cnf, variables)
    timing("end", "exactly_one")

    def add_overlap_clauses(direction, dx, dy):
        for y in range(height):
            for x in range(width):

                nx = x + dx
                ny = y + dy

                if nx < 0 or nx >= width or ny < 0 or ny >= height:
                    continue

                for p1 in patterns:
                    if adjacency_encoding == "support":
                        cnf.add_clause(
                            [-cnf.var_for(x, y, p1.id)]
                            + [
                                cnf.var_for(nx, ny, pattern_id)
                                for pattern_id in allowed[direction][p1.id]
                            ]
                        )
                    else:
                        for p2 in patterns:
                            if p2.id not in allowed[direction][p1.id]:
                                cnf.add_clause([
                                    -cnf.var_for(x, y, p1.id),
                                    -cnf.var_for(nx, ny, p2.id),
                                ])

    timing("start", "compatibility")
    add_overlap_clauses("right", 1, 0)
    add_overlap_clauses("down", 0, 1)
    timing("end", "compatibility")

    return cnf


def _add_sequential_at_most_one(cnf: CnfBuilder, variables: list[int]) -> None:
    """Sinz sequential-counter encoding of at-most-one over ``variables``."""
    if len(variables) <= 1:
        return
    sequential = [cnf.new_aux_var() for _ in range(len(variables) - 1)]
    cnf.add_clause([-variables[0], sequential[0]])
    for index in range(1, len(variables) - 1):
        cnf.add_clause([-variables[index], sequential[index]])
        cnf.add_clause([-sequential[index - 1], sequential[index]])
        cnf.add_clause([-variables[index], -sequential[index - 1]])
    cnf.add_clause([-variables[-1], -sequential[-1]])
