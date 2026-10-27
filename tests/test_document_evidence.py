"""Deterministic checks for document citations and causal attributions."""

from __future__ import annotations

from app.services.evidence_check import check_document_evidence


SOURCE = "management_report_2024-12.md"
CHUNK = {
    "document_name": SOURCE,
    "text": (
        "Management noted that supplier delays affected availability "
        "of several popular electronics products."
    ),
}


def test_document_claim_requires_matching_source_and_exact_quote() -> None:
    """Accept a document claim when its source and quoted passage are retrieved."""
    valid, issues = check_document_evidence(
        "The report mentions supplier delays "
        f"[{SOURCE}], “supplier delays affected availability”.",
        [CHUNK],
    )

    assert valid is True
    assert issues == []


def test_answer_without_a_document_citation_is_rejected_when_passage_exists() -> None:
    """A generic acknowledgement cannot pass as an answer to retrieved evidence."""
    valid, issues = check_document_evidence(
        "Thank you. I will cite the document next time.",
        [CHUNK],
    )

    assert valid is False
    assert any("does not cite a retrieved source" in issue for issue in issues)


def test_document_claim_rejects_a_source_not_in_retrieved_chunks() -> None:
    """A plausible but unreturned filename cannot support an attributed claim."""
    valid, issues = check_document_evidence(
        "The report mentions supplier delays [other_report.md], "
        "“supplier delays affected availability”.",
        [CHUNK],
    )

    assert valid is False
    assert any("do not match retrieved sources" in issue for issue in issues)


def test_document_claim_requires_an_exact_quote_from_the_cited_chunk() -> None:
    """A matching citation alone does not verify the attributed passage."""
    valid, issues = check_document_evidence(
        f"The report says inventory was depleted [{SOURCE}], "
        "“inventory was depleted”.",
        [CHUNK],
    )

    assert valid is False
    assert any("exact quoted passage" in issue for issue in issues)


def test_each_quote_in_a_cited_sentence_must_match_the_source() -> None:
    """One valid excerpt cannot be used to legitimize a second invented quote."""
    valid, issues = check_document_evidence(
        "The report mentions supplier delays "
        f"[{SOURCE}], “supplier delays affected availability”, "
        "and states that they reduced all sales "
        f"[{SOURCE}], “they reduced all sales”.",
        [CHUNK],
    )

    assert valid is False
    assert any("exact quoted passage" in issue for issue in issues)


def test_causal_claim_must_be_attributed_and_uncertain() -> None:
    """Do not present a possible reported factor as established causation."""
    unqualified, unqualified_issues = check_document_evidence(
        f"Supplier delays caused the December dip [{SOURCE}], "
        "“supplier delays affected availability”.",
        [CHUNK],
    )
    qualified, qualified_issues = check_document_evidence(
        "The report mentions supplier delays as a possible factor, "
        f"but does not establish causation [{SOURCE}], "
        "“supplier delays affected availability”.",
        [CHUNK],
    )

    assert unqualified is False
    assert any("causal explanation" in issue for issue in unqualified_issues)
    assert qualified is True
    assert qualified_issues == []
