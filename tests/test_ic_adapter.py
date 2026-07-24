from core.adapters.ic_adapter import ICAdapter

SAMPLE_IC_HTML = """
<html>
<body>
  <table>
    <tr>
      <th>Circular No.</th>
      <th>Subject</th>
      <th>Link</th>
    </tr>
    <tr>
      <td>CL No. 2026-05</td>
      <td>Guidelines on Microinsurance Product Licensing for Insurance Companies.</td>
      <td><a href="/wp-content/uploads/2026/CL2026_05.pdf">Download PDF</a></td>
    </tr>
    <tr>
      <td>Circular Letter No. 2026-01</td>
      <td>Revised Capital Adequacy Requirements for Life Insurance Companies.</td>
      <td><a href="/wp-content/uploads/2026/CL2026_01.pdf">Download PDF</a></td>
    </tr>
  </table>
</body>
</html>
"""


def test_ic_adapter_identifier_extraction():
    adapter = ICAdapter()

    id1 = adapter._extract_identifier("CL No. 2026-05 Microinsurance guidelines", "CL")
    assert id1 == "CL No. 2026-05"

    id2 = adapter._extract_identifier("Circular Letter No. 2026-01 Capital requirements", "CL")
    assert id2 == "Circular Letter No. 2026-01"


def test_ic_adapter_parse_html_page():
    adapter = ICAdapter()
    base_url = "https://www.insurance.gov.ph/category/circular-letters/"

    raw_issuances = adapter.parse_html_page(SAMPLE_IC_HTML, base_url, "CL")

    assert len(raw_issuances) == 2

    first = raw_issuances[0]
    assert first.regulator_id == "IC"
    assert first.category_id == "CL"
    assert first.raw_identifier == "CL No. 2026-05"
    assert first.pdf_url == "https://www.insurance.gov.ph/wp-content/uploads/2026/CL2026_05.pdf"


def test_ic_adapter_normalization():
    adapter = ICAdapter()
    base_url = "https://www.insurance.gov.ph/category/circular-letters/"

    raw_list = adapter.parse_html_page(SAMPLE_IC_HTML, base_url, "CL")
    normalized = adapter.normalize(raw_list[0])

    assert normalized.issuance_id == "IC_CL No. 2026-05"
    assert normalized.regulator_id == "IC"
    assert "Microinsurance" in normalized.title
