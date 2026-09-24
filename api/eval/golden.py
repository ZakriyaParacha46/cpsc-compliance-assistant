"""Golden questions for the retrieval eval.

`expect` lists sources that correctly answer the question: a CFR section ("1110.7"), a statute
section ("15 U.S.C. 2063"), or a whole guidance page by its document id ("cpsc-faq-gcc").
A question is a hit if ANY of them is in the top 6 chunks. Binding sources (rules and laws)
are also scored on their own, because a guidance page alone isn't enough to cite an obligation.

Out-of-scope questions (expect=None) must fall below the relevance threshold, so the app answers
"not covered" without calling the model.
"""

GOLDEN: list[dict] = [
    # The four example questions shown in the UI.
    {
        "q": "Do I need a Children's Product Certificate for a kids' LED night light?",
        "expect": [
            "1200.2",
            "1110.3",
            "15 U.S.C. 2063",
            "cpsc-testing-certification-childrens-product-certificate",
            "cpsc-faq-cpc",
            "cpsc-business-education-childrens-products",
        ],
    },
    {
        "q": "Who issues the General Certificate of Conformity, me or my factory?",
        "expect": [
            "1110.7",
            "15 U.S.C. 2063",
            "cpsc-faq-gcc",
            "cpsc-testing-certification-general-certificate-of-conformity",
            "cpsc-testing-certification-general-use-products-certification-and-testing",
        ],
    },
    {
        "q": "What does Reese's Law require for a device with a coin cell battery?",
        "expect": [
            "1263.3",
            "1263.1",
            "15 U.S.C. 2056e",
            "cpsc-business-education-business-guidance-button-cell-and-coin-battery",
            "cpsc-faq-button-cell-and-coin-battery-faqs",
        ],
    },
    {
        "q": "What documents must my suppliers give me as a retailer?",
        "expect": ["1110.13", "15 U.S.C. 2063", "cpsc-faq-gcc", "cpsc-faq-cpc"],
    },
    # Testing and certification details.
    {
        "q": "How many samples do I need to send to a third-party lab for certification testing?",
        "expect": ["1107.20"],
    },
    {
        "q": "How often must children's products be periodically tested?",
        "expect": ["1107.21"],
    },
    {
        "q": "Can I rely on component part testing done by my supplier?",
        "expect": ["1109.5", "1109.1", "1109.3", "1110.19"],
    },
    {
        "q": "How long must certificates and test records be kept?",
        "expect": ["1110.17", "1107.26"],
    },
    # Chemicals and materials.
    {
        "q": "What is the maximum lead content allowed in children's products?",
        "expect": ["15 U.S.C. 1278a", "cpsc-faq-total-lead-content"],
    },
    {
        "q": "What is the lead limit for paint on toys?",
        "expect": ["1303.1", "1303.2", "1303.4", "cpsc-faq-total-lead-content"],
    },
    {
        "q": "Which phthalates are banned in children's toys and child care articles?",
        "expect": [
            "1307.3",
            "15 U.S.C. 2057c",
            "cpsc-business-education-business-guidance-phthalates",
        ],
    },
    # Labels and toys.
    {
        "q": "What information must a tracking label on a children's product include?",
        "expect": ["15 U.S.C. 2063", "cpsc-business-education-tracking-label"],
    },
    {
        "q": "Which toys need a small parts choking hazard warning label?",
        "expect": [
            "1500.19",
            "15 U.S.C. 1278",
            "cpsc-faq-small-parts-and-choking-hazard-labeling-faqs",
        ],
    },
    {
        "q": "Which safety standard do toys have to comply with?",
        "expect": ["1250.2", "cpsc-faq-toy-safety"],
    },
    {
        "q": "What warnings must appear on the label of a hazardous household substance?",
        "expect": ["1500.121", "15 U.S.C. 1261", "1500.3"],
    },
    # Packaging and reporting.
    {
        "q": "Does packaging for button cell batteries need to be child-resistant?",
        "expect": [
            "1700.15",
            "1700.14",
            "15 U.S.C. 2056e",
            "cpsc-business-education-business-guidance-button-cell-and-coin-battery",
            "cpsc-faq-button-cell-and-coin-battery-faqs",
        ],
    },
    {
        "q": "How quickly must a company report a product defect to CPSC?",
        "expect": ["1115.14", "1115.12", "15 U.S.C. 2064"],
    },
    # Out of scope: other agencies or not product safety at all.
    {"q": "What are the FDA nutrition labeling rules for packaged snacks?", "expect": None},
    {"q": "How do I register a trademark for my brand name?", "expect": None},
    {"q": "What FCC certification does a Bluetooth speaker need?", "expect": None},
]


def is_binding(source_id: str) -> bool:
    return not source_id.startswith("cpsc-")
