"""Shared SCM emitters for per-giver mission order. No Archipelago imports."""

UNLOCK_FIRST = 9010
UNLOCK_LAST = 9029
ORDER_BASE = 9036
RANK_GLOBAL = 10166
DIGIT_GLOBAL = 10167
COMPLETED_GLOBAL = 10168


def order_global(unlock: int) -> int:
    return ORDER_BASE + unlock - UNLOCK_FIRST


def rank_lines(unlock: int, count: int, label: str) -> list[str]:
    """Decode a mission's rank; zero order preserves its vanilla rank.

    Each decimal digit holds one mission's rank, first mission in the units
    digit. Givers have at most five missions. Integer arithmetic needs no CLEO
    extension. The scratch globals are shared only across code with no waits.
    """
    order = order_global(unlock)
    return [f"${RANK_GLOBAL} = {count}",
            "if ", f"  ${order} > 0", f"goto_if_false @{label}",
            f"set_var_int_to_var_int ${RANK_GLOBAL} = ${order}", f"${RANK_GLOBAL} /= {10 ** (count - 1)}",
            f"set_var_int_to_var_int ${DIGIT_GLOBAL} = ${RANK_GLOBAL}", f"${DIGIT_GLOBAL} /= 10",
            f"${DIGIT_GLOBAL} *= 10", f"sub_int_var_from_int_var ${RANK_GLOBAL} -= ${DIGIT_GLOBAL}", f":{label}"]


def gate_lines(unlock: int, count: int, loopback: str, label: str) -> list[str]:
    return [*rank_lines(unlock, count, label),
            "if ", f"  is_int_var_greater_or_equal_to_int_var ${unlock} >= ${RANK_GLOBAL}",
            f"goto_if_false @{loopback}"]
