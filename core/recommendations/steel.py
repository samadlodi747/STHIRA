def beam_recommendation_sort_key(item: dict) -> tuple:
    profile = item["profile"]
    return (
        item.get("weight", float("inf")),
        profile.get("h", float("inf")) or float("inf"),
        item.get("governing", float("inf")),
        profile.get("n", ""),
    )
