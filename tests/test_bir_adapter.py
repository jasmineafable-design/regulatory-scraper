from core.adapters.bir_adapter import BIRAdapter


SAMPLE_BIR_HTML = """
<html>
<body>
  <table>
    <tr>
      <th>Issuance No</th>
      <th>Subject / Description</th>
      <th>File Download</th>
    </tr>
    <tr>
      <td>RMC No. 15-2026</td>
      <td>Publishes the revised guidelines on VAT zero-rated sales for exporters.</td>
      <td><a href="/images/pb/RMC%20No%2015-2026.pdf">Download PDF</a></td>
    </tr>
    <tr>
      <td>RR No. 02-2026</td>
      <td>Amending section 3 of Revenue Regulations No. 10-2021 regarding tax exemptions.</td>
      <td><a href="/images/pb/RR%20No%2002-2026.pdf">Download PDF</a></td>
    </tr>
  </table>
</body>
</html>
"""


def test_bir_adapter_identifier_extraction():
    adapter = BIRAdapter()
    
    id1 = adapter._extract_identifier("RMC No. 15-2026 Guidelines on VAT", "RMC")
    assert id1 == "RMC No. 15-2026"

    id2 = adapter._extract_identifier("Revenue Regulations RR No. 02-2026 Amending rules", "RR")
    assert id2 == "RR No. 02-2026"


def test_bir_adapter_parse_html_page():
    adapter = BIRAdapter()
    base_url = "https://www.bir.gov.ph/revenue-issuances-details"
    
    raw_issuances = adapter.parse_html_page(SAMPLE_BIR_HTML, base_url, "RMC")
    
    assert len(raw_issuances) == 2
    
    first = raw_issuances[0]
    assert first.regulator_id == "BIR"
    assert first.category_id == "RMC"
    assert first.raw_identifier == "RMC No. 15-2026"
    assert first.pdf_url == "https://www.bir.gov.ph/images/pb/RMC%20No%2015-2026.pdf"


def test_bir_adapter_normalization():
    adapter = BIRAdapter()
    base_url = "https://www.bir.gov.ph/revenue-issuances-details"
    
    raw_list = adapter.parse_html_page(SAMPLE_BIR_HTML, base_url, "RMC")
    normalized = adapter.normalize(raw_list[0])
    
    assert normalized.issuance_id == "BIR_RMC No. 15-2026"
    assert normalized.regulator_id == "BIR"
    assert "VAT zero-rated sales" in normalized.title
