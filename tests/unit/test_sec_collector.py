"""
Tests for SEC Collector - Parsing methods
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone, timedelta
from xml.etree import ElementTree
from bs4 import BeautifulSoup


class TestFindMainDocument:
    """Tests for _find_main_document method"""

    @pytest.fixture
    def collector(self):
        """Create collector instance"""
        with patch("src.collectors.sec_collector.get_settings") as mock_settings:
            mock_settings.return_value.sec.base_url = "https://www.sec.gov"
            mock_settings.return_value.sec.company_tickers_url = "https://www.sec.gov/files/company_tickers.json"
            mock_settings.return_value.sec.user_agent = "Test/1.0"
            mock_settings.return_value.sec.request_delay = 0.1
            mock_settings.return_value.sec.timeout = 30
            from src.collectors.sec_collector import SECCollector
            return SECCollector()

    def test_finds_8k_in_href(self, collector):
        """Finds 8-K document by href pattern"""
        html = '''
        <html>
            <a href="d8k.htm">8-K Document</a>
        </html>
        '''
        soup = BeautifulSoup(html, "lxml")
        result = collector._find_main_document(soup, "https://sec.gov/filings/test/")
        assert result == "https://sec.gov/filings/test/d8k.htm"

    def test_finds_8k_in_text(self, collector):
        """Finds 8-K document by link text"""
        html = '''
        <html>
            <a href="document.htm">Form 8-K Current Report</a>
        </html>
        '''
        soup = BeautifulSoup(html, "lxml")
        result = collector._find_main_document(soup, "https://sec.gov/filings/test/")
        assert result == "https://sec.gov/filings/test/document.htm"

    def test_finds_form8k_pattern(self, collector):
        """Finds document with form8k pattern"""
        html = '''
        <html>
            <a href="form8k_2025.html">Filing</a>
        </html>
        '''
        soup = BeautifulSoup(html, "lxml")
        result = collector._find_main_document(soup, "https://sec.gov/filings/test/")
        assert result == "https://sec.gov/filings/test/form8k_2025.html"

    def test_finds_8k_in_table(self, collector):
        """Finds 8-K document in table format"""
        html = '''
        <html>
            <table class="tableFile">
                <tr><th>Type</th></tr>
                <tr>
                    <td>1</td>
                    <td>2</td>
                    <td><a href="doc.htm">Link</a></td>
                    <td>8-K</td>
                </tr>
            </table>
        </html>
        '''
        soup = BeautifulSoup(html, "lxml")
        result = collector._find_main_document(soup, "https://sec.gov/filings/test/")
        assert result == "https://sec.gov/filings/test/doc.htm"

    def test_returns_none_when_not_found(self, collector):
        """Returns None when no 8-K document found"""
        html = '''
        <html>
            <a href="other.pdf">Some other document</a>
        </html>
        '''
        soup = BeautifulSoup(html, "lxml")
        result = collector._find_main_document(soup, "https://sec.gov/filings/test/")
        assert result is None

    def test_handles_absolute_url(self, collector):
        """Handles absolute URLs in href"""
        html = '''
        <html>
            <a href="https://sec.gov/absolute/8k.htm">8-K</a>
        </html>
        '''
        soup = BeautifulSoup(html, "lxml")
        result = collector._find_main_document(soup, "https://sec.gov/filings/test/")
        assert result == "https://sec.gov/absolute/8k.htm"


class TestBuildFullUrl:
    """Tests for _build_full_url method"""

    @pytest.fixture
    def collector(self):
        """Create collector instance"""
        with patch("src.collectors.sec_collector.get_settings") as mock_settings:
            mock_settings.return_value.sec.base_url = "https://www.sec.gov"
            mock_settings.return_value.sec.company_tickers_url = "https://www.sec.gov/files/company_tickers.json"
            mock_settings.return_value.sec.user_agent = "Test/1.0"
            mock_settings.return_value.sec.request_delay = 0.1
            mock_settings.return_value.sec.timeout = 30
            from src.collectors.sec_collector import SECCollector
            return SECCollector()

    def test_relative_url(self, collector):
        """Builds full URL from relative href"""
        result = collector._build_full_url("doc.htm", "https://sec.gov/filings/abc/index.htm")
        assert result == "https://sec.gov/filings/abc/doc.htm"

    def test_absolute_url_unchanged(self, collector):
        """Absolute URLs pass through unchanged"""
        result = collector._build_full_url("https://other.com/doc.htm", "https://sec.gov/filings/")
        assert result == "https://other.com/doc.htm"

    def test_absolute_path_uses_base_domain(self, collector):
        """Absolute paths (starting with /) use base domain only"""
        result = collector._build_full_url(
            "/Archives/edgar/data/123/form4.xml",
            "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
        )
        assert result == "https://www.sec.gov/Archives/edgar/data/123/form4.xml"

    def test_absolute_path_no_double_slashes(self, collector):
        """Absolute paths don't create double slashes in URL"""
        result = collector._build_full_url(
            "/Archives/edgar/data/1652044/000119312525338475/xslF345X05/ownership.xml",
            "https://www.sec.gov/Archives/edgar/data/1652044/000119312525338475/0001193125-25-338475-index.htm"
        )
        assert "//" not in result.replace("https://", "")
        assert result == "https://www.sec.gov/Archives/edgar/data/1652044/000119312525338475/xslF345X05/ownership.xml"


class TestFindForm4Xml:
    """Tests for _find_form4_xml method"""

    @pytest.fixture
    def collector(self):
        """Create collector instance"""
        with patch("src.collectors.sec_collector.get_settings") as mock_settings:
            mock_settings.return_value.sec.base_url = "https://www.sec.gov"
            mock_settings.return_value.sec.company_tickers_url = "https://www.sec.gov/files/company_tickers.json"
            mock_settings.return_value.sec.user_agent = "Test/1.0"
            mock_settings.return_value.sec.request_delay = 0.1
            mock_settings.return_value.sec.timeout = 30
            from src.collectors.sec_collector import SECCollector
            return SECCollector()

    def test_finds_raw_xml_file(self, collector):
        """Finds raw XML file in filing index"""
        html = '''
        <html>
            <a href="wk-form4_123456.xml">XML</a>
        </html>
        '''
        soup = BeautifulSoup(html, "lxml")
        result = collector._find_form4_xml(soup, "https://sec.gov/filings/test/")
        assert result == "https://sec.gov/filings/test/wk-form4_123456.xml"

    def test_skips_xslt_transformed_files(self, collector):
        """Skips XSLT-transformed XML files (they return HTML)"""
        html = '''
        <html>
            <a href="xslF345X05/ownership.xml">Styled XML</a>
            <a href="wk-form4_123456.xml">Raw XML</a>
        </html>
        '''
        soup = BeautifulSoup(html, "lxml")
        result = collector._find_form4_xml(soup, "https://sec.gov/filings/test/")
        # Should return the raw XML, not the XSLT one
        assert result == "https://sec.gov/filings/test/wk-form4_123456.xml"

    def test_returns_none_when_only_xslt_available(self, collector):
        """Returns None when only XSLT files are available"""
        html = '''
        <html>
            <a href="/Archives/edgar/xslF345X05/ownership.xml">Styled XML</a>
        </html>
        '''
        soup = BeautifulSoup(html, "lxml")
        result = collector._find_form4_xml(soup, "https://sec.gov/filings/test/")
        assert result is None


class TestExtract8kItems:
    """Tests for _extract_8k_items method"""

    @pytest.fixture
    def collector(self):
        """Create collector instance"""
        with patch("src.collectors.sec_collector.get_settings") as mock_settings:
            mock_settings.return_value.sec.base_url = "https://www.sec.gov"
            mock_settings.return_value.sec.company_tickers_url = "https://www.sec.gov/files/company_tickers.json"
            mock_settings.return_value.sec.user_agent = "Test/1.0"
            mock_settings.return_value.sec.request_delay = 0.1
            mock_settings.return_value.sec.timeout = 30
            from src.collectors.sec_collector import SECCollector
            return SECCollector()

    def test_extracts_single_item(self, collector):
        """Extracts single item number"""
        text = "Item 5.02 Departure of Directors"
        result = collector._extract_8k_items(text)
        assert "5.02 - Departure/Appointment of Directors or Officers" in result

    def test_extracts_multiple_items(self, collector):
        """Extracts multiple items"""
        text = "Item 4.01 Changes in Accountant\nItem 4.02 Non-Reliance on Financial Statements"
        result = collector._extract_8k_items(text)
        assert len(result) == 2
        assert "4.01 - Changes in Registrant's Certifying Accountant" in result
        assert "4.02 - Non-Reliance on Financial Statements" in result

    def test_handles_no_items(self, collector):
        """Returns empty list when no items found"""
        text = "This is a general document with no item numbers."
        result = collector._extract_8k_items(text)
        assert result == []

    def test_case_insensitive(self, collector):
        """Item detection is case insensitive"""
        text = "ITEM 2.05 COSTS FOR EXIT ACTIVITIES"
        result = collector._extract_8k_items(text)
        assert "2.05 - Costs for Exit Activities" in result


class TestGetXmlHelpers:
    """Tests for XML helper methods"""

    @pytest.fixture
    def collector(self):
        """Create collector instance"""
        with patch("src.collectors.sec_collector.get_settings") as mock_settings:
            mock_settings.return_value.sec.base_url = "https://www.sec.gov"
            mock_settings.return_value.sec.company_tickers_url = "https://www.sec.gov/files/company_tickers.json"
            mock_settings.return_value.sec.user_agent = "Test/1.0"
            mock_settings.return_value.sec.request_delay = 0.1
            mock_settings.return_value.sec.timeout = 30
            from src.collectors.sec_collector import SECCollector
            return SECCollector()

    def test_get_xml_text_found(self, collector):
        """Returns text when element exists"""
        xml = "<root><name>  John Smith  </name></root>"
        root = ElementTree.fromstring(xml)
        result = collector._get_xml_text(root, ".//name")
        assert result == "John Smith"

    def test_get_xml_text_not_found(self, collector):
        """Returns None when element missing"""
        xml = "<root><other>value</other></root>"
        root = ElementTree.fromstring(xml)
        result = collector._get_xml_text(root, ".//name")
        assert result is None

    def test_get_xml_text_empty(self, collector):
        """Returns None for empty element"""
        xml = "<root><name></name></root>"
        root = ElementTree.fromstring(xml)
        result = collector._get_xml_text(root, ".//name")
        assert result is None

    def test_get_xml_float_valid(self, collector):
        """Returns float when valid number"""
        xml = "<root><price><value>150.50</value></price></root>"
        root = ElementTree.fromstring(xml)
        result = collector._get_xml_float(root, ".//price/value")
        assert result == 150.50

    def test_get_xml_float_invalid(self, collector):
        """Returns None for invalid number"""
        xml = "<root><price><value>not a number</value></price></root>"
        root = ElementTree.fromstring(xml)
        result = collector._get_xml_float(root, ".//price/value")
        assert result is None

    def test_get_xml_float_missing(self, collector):
        """Returns None for missing element"""
        xml = "<root><other>value</other></root>"
        root = ElementTree.fromstring(xml)
        result = collector._get_xml_float(root, ".//price/value")
        assert result is None


class TestParseAtomDate:
    """Tests for filing date parsing from Atom feed"""

    @pytest.fixture
    def collector(self):
        """Create collector instance"""
        with patch("src.collectors.sec_collector.get_settings") as mock_settings:
            mock_settings.return_value.sec.base_url = "https://www.sec.gov"
            mock_settings.return_value.sec.company_tickers_url = "https://www.sec.gov/files/company_tickers.json"
            mock_settings.return_value.sec.user_agent = "Test/1.0"
            mock_settings.return_value.sec.request_delay = 0.1
            mock_settings.return_value.sec.timeout = 30
            from src.collectors.sec_collector import SECCollector
            return SECCollector()

    def test_prefers_filing_date_over_updated(self, collector):
        """Prefers filing-date element over updated element"""
        import asyncio
        # Use dates relative to a fixed cutoff to avoid time-dependent failures
        filing_date = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%d")
        updated_date = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%dT10:00:00Z")

        xml = f'''<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <entry>
                <title>8-K Test Filing</title>
                <link href="https://sec.gov/test"/>
                <filing-date>{filing_date}</filing-date>
                <updated>{updated_date}</updated>
            </entry>
        </feed>
        '''
        root = ElementTree.fromstring(xml)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entry = root.find("atom:entry", ns)
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)

        result = asyncio.run(collector._parse_8k_entry(entry, ns, cutoff))

        # Should use filing-date, not updated
        assert result is not None
        assert result.date == filing_date

    def test_falls_back_to_updated(self, collector):
        """Falls back to updated when filing-date missing"""
        import asyncio
        updated_date = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%dT10:00:00Z")
        expected_date = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%d")

        xml = f'''<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <entry>
                <title>8-K Test Filing</title>
                <link href="https://sec.gov/test"/>
                <updated>{updated_date}</updated>
            </entry>
        </feed>
        '''
        root = ElementTree.fromstring(xml)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entry = root.find("atom:entry", ns)
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)

        result = asyncio.run(collector._parse_8k_entry(entry, ns, cutoff))

        assert result is not None
        assert result.date == expected_date

    def test_returns_none_when_no_date(self, collector):
        """Returns None when no date element exists"""
        import asyncio
        xml = '''<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <entry>
                <title>8-K Test Filing</title>
                <link href="https://sec.gov/test"/>
            </entry>
        </feed>
        '''
        root = ElementTree.fromstring(xml)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entry = root.find("atom:entry", ns)
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)

        result = asyncio.run(collector._parse_8k_entry(entry, ns, cutoff))

        assert result is None


class TestHasNewFilings8k:
    """Tests for has_new_filings_8k method"""

    @pytest.fixture
    def collector(self):
        """Create collector instance"""
        with patch("src.collectors.sec_collector.get_settings") as mock_settings:
            mock_settings.return_value.sec.base_url = "https://www.sec.gov"
            mock_settings.return_value.sec.company_tickers_url = "https://www.sec.gov/files/company_tickers.json"
            mock_settings.return_value.sec.user_agent = "Test/1.0"
            mock_settings.return_value.sec.request_delay = 0.01
            mock_settings.return_value.sec.timeout = 30
            from src.collectors.sec_collector import SECCollector
            return SECCollector()

    @pytest.mark.asyncio
    async def test_returns_true_when_new_filings_exist(self, collector):
        """Returns True when filings exist after since_date"""
        mock_response = MagicMock()
        mock_response.content = b'''<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <entry>
                <filing-date>2024-01-20</filing-date>
            </entry>
        </feed>
        '''
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        collector._get_client = AsyncMock(return_value=mock_client)
        collector._get_cik = AsyncMock(return_value="0001234567890")
        collector._rate_limit = AsyncMock()

        result = await collector.has_new_filings_8k("AAPL", "2024-01-15")

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_no_new_filings(self, collector):
        """Returns False when no filings after since_date"""
        mock_response = MagicMock()
        mock_response.content = b'''<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <entry>
                <filing-date>2024-01-10</filing-date>
            </entry>
        </feed>
        '''
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        collector._get_client = AsyncMock(return_value=mock_client)
        collector._get_cik = AsyncMock(return_value="0001234567890")
        collector._rate_limit = AsyncMock()

        result = await collector.has_new_filings_8k("AAPL", "2024-01-15")

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_cik_not_found(self, collector):
        """Returns False when CIK cannot be resolved"""
        collector._get_cik = AsyncMock(return_value=None)

        result = await collector.has_new_filings_8k("INVALID", "2024-01-15")

        assert result is False


class TestHasNewFilingsForm4:
    """Tests for has_new_filings_form4 method"""

    @pytest.fixture
    def collector(self):
        """Create collector instance"""
        with patch("src.collectors.sec_collector.get_settings") as mock_settings:
            mock_settings.return_value.sec.base_url = "https://www.sec.gov"
            mock_settings.return_value.sec.company_tickers_url = "https://www.sec.gov/files/company_tickers.json"
            mock_settings.return_value.sec.user_agent = "Test/1.0"
            mock_settings.return_value.sec.request_delay = 0.01
            mock_settings.return_value.sec.timeout = 30
            from src.collectors.sec_collector import SECCollector
            return SECCollector()

    @pytest.mark.asyncio
    async def test_returns_true_when_new_filings_exist(self, collector):
        """Returns True when Form 4 filings exist after since_date"""
        mock_response = MagicMock()
        mock_response.content = b'''<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <entry>
                <filing-date>2024-01-20</filing-date>
            </entry>
        </feed>
        '''
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        collector._get_client = AsyncMock(return_value=mock_client)
        collector._get_cik = AsyncMock(return_value="0001234567890")
        collector._rate_limit = AsyncMock()

        result = await collector.has_new_filings_form4("AAPL", "2024-01-15")

        assert result is True


class TestGetLatestFilingDates:
    """Tests for get_latest_filing_dates method"""

    @pytest.fixture
    def collector(self):
        """Create collector instance"""
        with patch("src.collectors.sec_collector.get_settings") as mock_settings:
            mock_settings.return_value.sec.base_url = "https://www.sec.gov"
            mock_settings.return_value.sec.company_tickers_url = "https://www.sec.gov/files/company_tickers.json"
            mock_settings.return_value.sec.user_agent = "Test/1.0"
            mock_settings.return_value.sec.request_delay = 0.01
            mock_settings.return_value.sec.timeout = 30
            from src.collectors.sec_collector import SECCollector
            return SECCollector()

    @pytest.mark.asyncio
    async def test_returns_both_dates(self, collector):
        """Returns both 8-K and Form 4 dates"""
        mock_response = MagicMock()
        mock_response.content = b'''<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <entry>
                <filing-date>2024-01-20</filing-date>
            </entry>
        </feed>
        '''
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        collector._get_client = AsyncMock(return_value=mock_client)
        collector._get_cik = AsyncMock(return_value="0001234567890")
        collector._rate_limit = AsyncMock()

        latest_8k, latest_form4 = await collector.get_latest_filing_dates("AAPL")

        assert latest_8k == "2024-01-20"
        assert latest_form4 == "2024-01-20"

    @pytest.mark.asyncio
    async def test_returns_none_when_cik_not_found(self, collector):
        """Returns None for both when CIK not found"""
        collector._get_cik = AsyncMock(return_value=None)

        latest_8k, latest_form4 = await collector.get_latest_filing_dates("INVALID")

        assert latest_8k is None
        assert latest_form4 is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_filings(self, collector):
        """Returns None when no filings found"""
        mock_response = MagicMock()
        mock_response.content = b'''<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
        </feed>
        '''
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        collector._get_client = AsyncMock(return_value=mock_client)
        collector._get_cik = AsyncMock(return_value="0001234567890")
        collector._rate_limit = AsyncMock()

        latest_8k, latest_form4 = await collector.get_latest_filing_dates("AAPL")

        assert latest_8k is None
        assert latest_form4 is None


class TestGetEntryDate:
    """Tests for _get_entry_date helper method"""

    @pytest.fixture
    def collector(self):
        """Create collector instance"""
        with patch("src.collectors.sec_collector.get_settings") as mock_settings:
            mock_settings.return_value.sec.base_url = "https://www.sec.gov"
            mock_settings.return_value.sec.company_tickers_url = "https://www.sec.gov/files/company_tickers.json"
            mock_settings.return_value.sec.user_agent = "Test/1.0"
            mock_settings.return_value.sec.request_delay = 0.01
            mock_settings.return_value.sec.timeout = 30
            from src.collectors.sec_collector import SECCollector
            return SECCollector()

    def test_prefers_filing_date(self, collector):
        """Prefers filing-date over updated"""
        xml = '''<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <entry>
                <filing-date>2024-01-15</filing-date>
                <updated>2024-01-20T10:00:00Z</updated>
            </entry>
        </feed>
        '''
        root = ElementTree.fromstring(xml)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entry = root.find("atom:entry", ns)

        result = collector._get_entry_date(entry, ns)

        assert result is not None
        assert result.strftime("%Y-%m-%d") == "2024-01-15"

    def test_falls_back_to_updated(self, collector):
        """Falls back to updated when filing-date missing"""
        xml = '''<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <entry>
                <updated>2024-01-20T10:00:00Z</updated>
            </entry>
        </feed>
        '''
        root = ElementTree.fromstring(xml)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entry = root.find("atom:entry", ns)

        result = collector._get_entry_date(entry, ns)

        assert result is not None
        assert result.strftime("%Y-%m-%d") == "2024-01-20"

    def test_returns_none_when_no_date(self, collector):
        """Returns None when no date elements exist"""
        xml = '''<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <entry>
                <title>Test</title>
            </entry>
        </feed>
        '''
        root = ElementTree.fromstring(xml)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entry = root.find("atom:entry", ns)

        result = collector._get_entry_date(entry, ns)

        assert result is None
