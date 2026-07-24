from core.adapters.ic_adapter import ICAdapter

SAMPLE_IC_CL_HTML = """
<html>
<body>
  <table>
    <thead>
      <tr><th>Circular No.</th><th>Subject</th><th>Link</th></tr>
    </thead>
    <tbody>
      <tr>
        <td>CL No. 2026-05</td>
        <td>Guidelines on Microinsurance Product Licensing.</td>
        <td><a href="/wp-content/uploads/2026/CL2026_05.pdf">Download PDF</a></td>
      </tr>
      <tr>
        <td>Circular Letter No. 2026-01</td>
        <td>Capital Adequacy Requirements for Life Insurers.</td>
        <td><a href="/wp-content/uploads/2026/CL2026_01.pdf">Download PDF</a></td>
      </tr>
    </tbody>
  </table>
</body>
</html>
"""

SAMPLE_IC_MULTI_HTML = """
<html>
<body>
  <table>
    <thead>
      <tr><th>Number</th><th>Title</th><th>Download</th></tr>
    </thead>
    <tbody>
      <tr>
        <td>Advisory No. 2026-02</td>
        <td>Public Advisory on Unauthorized Solicitations.</td>
        <td><a href="/wp-content/uploads/2026/Adv2026_02.pdf">Download</a></td>
      </tr>
      <tr>
        <td>MC No. 2026-01</td>
        <td>Memorandum Circular on Electronic Governance Filings.</td>
        <td><a href="/wp-content/uploads/2026/MC2026_01.pdf">Download</a></td>
      </tr>
    </tbody>
  </table>
</body>
</html>
"""


def test_ic_adapter_identifier_extraction_all_types():
    adapter = ICAdapter()

    # Circular Letters
    assert adapter._extract_identifier("CL No. 2026-05 Guidelines", "CL") == "CL No. 2026-05"
    assert adapter._extract_identifier("Circular Letter No. 2026-01 Rules", "CL") == "Circular Letter No. 2026-01"

    # Advisories
    assert adapter._extract_identifier("Advisory No. 2026-02 Warning notice", "ADV") == "Advisory No. 2026-02"

    # Memorandum Circulars
    assert adapter._extract_identifier("MC No. 2026-01 E-Governance", "MC") == "MC No. 2026-01"
    assert adapter._extract_identifier("Memorandum Circular No. 2026-03 Filings", "MC") == "Memorandum Circular No. 2026-03"


def test_ic_adapter_parse_cl_page():
    adapter = ICAdapter()
    base_url = "https://www.insurance.gov.ph/category/circular-letters/"

    raw_issuances = adapter.parse_html_page(SAMPLE_IC_CL_HTML, base_url, "CL")
    assert len(raw_issuances) == 2
    assert raw_issuances[0].raw_identifier == "CL No. 2026-05"


def test_ic_adapter_parse_advisory_and_mc_page():
    adapter = ICAdapter()
    base_url = "https://www.insurance.gov.ph/category/advisories/"

    raw_issuances = adapter.parse_html_page(SAMPLE_IC_MULTI_HTML, base_url, "ADV")
    assert len(raw_issuances) == 2

    # Verify Advisory extraction
    adv_item = raw_issuances[0]
    assert adv_item.raw_identifier == "Advisory No. 2026-02"

    # Verify Memorandum Circular extraction
    mc_item = raw_issuances[1]
    assert mc_item.raw_identifier == "MC No. 2026-01"


def test_ic_adapter_normalization():
    adapter = ICAdapter()
    base_url = "https://www.insurance.gov.ph/category/circular-letters/"

    raw_list = adapter.parse_html_page(SAMPLE_IC_CL_HTML, base_url, "CL")
    normalized = adapter.normalize(raw_list[0])

    assert normalized.issuance_id == "IC_CL No. 2026-05"
    assert normalized.regulator_id == "IC"
    assert "Microinsurance" in normalized.title
