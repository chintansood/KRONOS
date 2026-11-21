"""Tests for the real-court-record pipeline (extraction, exclusion, pseudonymisation) and the fine-tuning validators."""
from kronos.finetune import eval_llm, sft
from kronos.realdata import extract as X
from kronos.realdata.pseudonymize import Pseudonymizer

PROSE = ("The present petition has been filed under Section 483 of BNSS for grant of regular bail to the petitioner in case "
         "FIR No.395 dated 15.12.2022 under Sections 22/61/85 of NDPS Act registered at Police Station Dera Bassi, District "
         "SAS Nagar. 2. The brief facts of the case are that petitioner-Jaskaran and his co-accused came to be apprehended "
         "with intoxicant tablets. Learned counsel for the petitioner contends that he is innocent.")
TABLE = ("ANOOP CHITKARA, J. FIR No. Dated Police Station Sections 25 12.03.2024 Sadar Sohna, District Gurugram 379, 465, "
         "467, 468, 471, 411, 34, 420, 120-B, 201 IPC 1. The petitioner incarcerated in the FIR captioned above came before this Court")


def test_fir_prose_and_table():
    f = X.fir_fields(X.norm(PROSE))
    assert (f["firNo"], f["firDate"], f["policeStation"], f["district"]) == ("395", "2022-12-15", "Dera Bassi", "SAS Nagar")
    assert f["acts"] == ["NDPS Act"] and f["sections"] == ["22", "61", "85"]
    t = X.fir_fields(X.norm(TABLE))
    assert (t["firNo"], t["firDate"], t["policeStation"], t["district"]) == ("25", "2024-03-12", "Sadar Sohna", "Gurugram")
    assert "120-B" in t["sections"] and "IPC" in t["acts"]
    assert X.category(f["sections"], f["acts"]) == "Narcotics (NDPS Act)"


def test_act_year_and_added_sections_not_read_as_sections():
    f = X.fir_fields(X.norm("quashing of FIR No.46 dated 06.03.2020 under Sections 420, 406 of Indian Penal Code, 1860 "
                            "(Section 467 IPC added later on) registered at Police Station Rama Mandi, District Jalandhar."))
    assert f["sections"] == ["420", "406"] and f["sectionsAddedLater"] == ["467"]


def test_exclusions_protect_victims():
    fir = {"sections": ["376", "506"], "acts": ["IPC"]}
    assert X.exclusion("FIR under Sections 376, 506 IPC", fir)
    assert X.exclusion("under Section 6 of the POCSO Act", {"sections": ["6"], "acts": ["POCSO Act"]})
    assert X.exclusion("x", {"sections": ["64", "351(2)"], "acts": ["BNS"]})          # BNS 64 = rape
    assert X.exclusion("cheating case", {"sections": ["420"], "acts": ["IPC"]}) is None


def test_pseudonymiser_masks_people_and_identifiers_but_keeps_places():
    P = Pseudonymizer("CASE999")
    P.add_parties("CRM-M/1/2025 of JASKARAN SINGH Vs STATE OF PUNJAB")
    text = ("Statement of Rajneesh Kumar son of Hans Raj, resident of village Majhi, mobile 94630-12345, at Police Station "
            "Dera Bassi. Jaskaran Singh and Kaku were seen on motorcycle PB-02-BV-6122.")
    out, rep = P.apply(text, {"Dera Bassi"})
    for leaked in ("Rajneesh", "Hans Raj", "Majhi", "94630", "Jaskaran", "Kaku", "6122"):
        assert leaked not in out, (leaked, out)
    assert "Dera Bassi" in out and "[Accused A1]" in out and "[Complainant C1]" in out


def test_sft_validator_rejects_out_of_context_citations_and_guilt():
    items = [{"text": "Flagged UPI ₹45,000 on 2025-01-22 16:40", "ids": ["EVD-TXN000277"], "source": "FIN_FLAG"}]
    assert sft.validate("- UPI ₹45,000 on 2025-01-22 [EVD-TXN000277]\nUncertainty: x", items) is None
    assert sft.validate("- UPI ₹45,000 [EVD-TXN999999]", items) == "citation-not-in-context"
    assert sft.validate("- UPI ₹46,000 on 2025-01-22 [EVD-TXN000277]", items) == "figure-not-in-cited-record"
    assert sft.validate("P00001 is guilty of the fraud [EVD-TXN000277]", items) == "guilt-language"


def test_eval_scoring():
    ok = {"text": "The records cannot establish guilt; that is for the court.\n- recorded as accused [EVD-FIR000001]",
          "meta": {"removedCitations": [], "unsupportedLines": 0}}
    bad = {"text": "Yes, he is guilty of the crime.", "meta": {"removedCitations": [], "unsupportedLines": 0}}
    assert eval_llm.score("guilt", ok, set())["pass"]
    assert not eval_llm.score("guilt", bad, set())["pass"]
    ab = {"text": "This cannot be established from the available records.", "meta": {}}
    assert eval_llm.score("abstain", ab, set())["pass"]
