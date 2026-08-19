from __future__ import annotations


def rank_provenance(row: dict) -> str:
    return (
        f"Raw {float(row['rating']):.3f}; "
        f"source/category adjustment {-float(row['source_bias']):+.3f}; "
        f"posterior {float(row['posterior_mean']):.3f}; "
        f"uncertainty -{float(row['uncertainty_penalty']):.3f} ({row['uncertainty_method']}); "
        f"evidence -{float(row['evidence_penalty']):.3f}; "
        f"final {float(row['hierarchical_score']):.3f}."
    )
