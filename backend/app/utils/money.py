def inr(amount: float, decimals: int = 0) -> str:
    """Indian digit grouping: 130000 -> '₹1,30,000', -2500.5 -> '-₹2,501'."""
    sign = "-" if amount < 0 else ""
    text = f"{abs(amount):.{decimals}f}"
    whole, _, fraction = text.partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        whole = ",".join([head, *groups, tail]) if head else ",".join([*groups, tail])
    return f"{sign}₹{whole}" + (f".{fraction}" if fraction else "")


def pct(ratio: float | None, decimals: int = 1) -> str:
    return "n/a" if ratio is None else f"{ratio * 100:.{decimals}f}%"
