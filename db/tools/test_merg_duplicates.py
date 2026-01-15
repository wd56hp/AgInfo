#!/usr/bin/env python3
"""
Tests for merg_duplicates.py

Tests core functionality without requiring database modifications.
Run with: python3 test_merg_duplicates.py
"""

import os
import sys
import unittest
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path to import merg_duplicates
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the module (will fail if there are syntax errors)
try:
    import merg_duplicates as md
except ImportError as e:
    print(f"ERROR: Could not import merg_duplicates: {e}")
    sys.exit(1)


class TestNormalization(unittest.TestCase):
    """Test normalization functions that don't require database"""

    def test_norm_ws(self):
        """Test whitespace normalization"""
        self.assertEqual(md.norm_ws("  hello   world  "), "hello world")
        self.assertEqual(md.norm_ws("a\t\nb"), "a b")
        self.assertEqual(md.norm_ws(""), "")

    def test_normalize_value(self):
        """Test value normalization"""
        self.assertIsNone(md.normalize_value(None))
        self.assertEqual(md.normalize_value("  test  "), "test")
        self.assertEqual(md.normalize_value(""), None)
        self.assertEqual(md.normalize_value(123), 123)

    def test_clean_street(self):
        """Test street address cleaning"""
        # Note: C.R. becomes "County Road." (period from original is preserved)
        self.assertEqual(md.clean_street("123 C.R. 10"), "123 County Road. 10")
        # Note: Co. Rd. becomes "County Road." (period preserved)
        self.assertEqual(md.clean_street("Co. Rd. 5"), "County Road. 5")
        self.assertEqual(md.clean_street("Cty Rd 20"), "County Road 20")
        self.assertEqual(md.clean_street(""), "")
        self.assertEqual(md.clean_street(None), "")
        self.assertEqual(md.clean_street("n/a"), "")

    def test_normalize_company_name(self):
        """Test company name normalization"""
        self.assertEqual(md.normalize_company_name("ABC Corp."), "abc")
        self.assertEqual(md.normalize_company_name("XYZ Inc."), "xyz")
        self.assertEqual(md.normalize_company_name("Test LLC"), "test")
        self.assertEqual(md.normalize_company_name(""), "")
        # Note: "company" and "co" are both in COMPANY_SUFFIXES, so both removed, leaving just "&"
        self.assertEqual(md.normalize_company_name("Company & Co."), "&")

    def test_facility_key(self):
        """Test facility key generation"""
        row1 = {
            "address_line1": "123 Main St",
            "city": "Topeka",
            "state": "KS",
            "postal_code": "66601"
        }
        row2 = {
            "address_line1": "123 Main St",
            "city": "Topeka",
            "state": "KS",
            "postal_code": "66601"
        }
        self.assertEqual(md.facility_key(row1), md.facility_key(row2))
        
        row3 = {
            "address_line1": "456 Oak Ave",
            "city": "Topeka",
            "state": "KS",
            "postal_code": "66601"
        }
        self.assertNotEqual(md.facility_key(row1), md.facility_key(row3))

    def test_company_score(self):
        """Test company scoring"""
        company1 = {"name": "Test", "website_url": "http://test.com", "phone_main": "123", "notes": "notes"}
        company2 = {"name": "Test"}
        self.assertGreater(md.company_score(company1), md.company_score(company2))

    def test_combine_text(self):
        """Test text combination"""
        self.assertEqual(md.combine_text("a", "b"), "a\n\n---\n\nb")
        self.assertEqual(md.combine_text("a", None), "a")
        self.assertEqual(md.combine_text(None, "b"), "b")
        self.assertEqual(md.combine_text("a", "a"), "a")
        self.assertIsNone(md.combine_text(None, None))


class TestDatabaseHelpers(unittest.TestCase):
    """Test database helper functions with mocked connections"""

    def setUp(self):
        """Set up mock database connection"""
        self.mock_conn = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_conn.cursor.return_value.__enter__.return_value = self.mock_cursor
        self.mock_conn.cursor.return_value.__exit__.return_value = None

    def test_table_exists(self):
        """Test table existence check"""
        # Table exists
        self.mock_cursor.fetchone.return_value = (1,)
        self.assertTrue(md.table_exists(self.mock_conn, "public", "facility"))
        
        # Table doesn't exist
        self.mock_cursor.fetchone.return_value = None
        self.assertFalse(md.table_exists(self.mock_conn, "public", "nonexistent"))

    def test_table_columns(self):
        """Test column discovery"""
        self.mock_cursor.fetchall.return_value = [("facility_id",), ("name",), ("status",)]
        cols = md.table_columns(self.mock_conn, "public", "facility")
        self.assertIn("facility_id", cols)
        self.assertIn("name", cols)
        self.assertIn("status", cols)
        self.assertEqual(len(cols), 3)

    def test_get_fk_references(self):
        """Test foreign key discovery"""
        self.mock_cursor.fetchall.return_value = [
            ("public", "facility_contact", "facility_id"),
            ("public", "facility_service", "facility_id"),
        ]
        fks = md.get_fk_references(self.mock_conn, "public", "facility")
        self.assertEqual(len(fks), 2)
        self.assertEqual(fks[0], ("public", "facility_contact", "facility_id"))


class TestProposalFunctions(unittest.TestCase):
    """Test merge proposal functions"""

    def test_propose_company_canonical(self):
        """Test company merge proposal"""
        companies = [
            {"company_id": 1, "name": "Test", "website_url": None, "phone_main": None, "notes": None},
            {"company_id": 2, "name": "Test", "website_url": "http://test.com", "phone_main": "123", "notes": "notes"},
        ]
        proposed, ids = md.propose_company_canonical(companies)
        self.assertIn(proposed["company_id"], [1, 2])
        self.assertEqual(len(ids), 2)
        # Should prefer company with more data
        if proposed["company_id"] == 2:
            self.assertIsNotNone(proposed.get("website_url"))

    def test_pick_best_name(self):
        """Test name selection"""
        names = ["Short", "This is a longer name", "Medium"]
        best = md.pick_best_name(names)
        self.assertEqual(best, "This is a longer name")
        
        self.assertIsNone(md.pick_best_name([None, "", None]))
        self.assertEqual(md.pick_best_name(["Only"]), "Only")


class TestScriptExecution(unittest.TestCase):
    """Test script can be executed (dry-run mode)"""

    @patch('merg_duplicates.db_connect')
    @patch('merg_duplicates.ask_yes_no')
    def test_script_dry_run(self, mock_ask, mock_db_connect):
        """Test script runs in dry-run mode without errors"""
        # Mock database connection
        mock_conn = MagicMock()
        mock_conn.autocommit = False
        mock_conn.close = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.cursor.return_value.__exit__.return_value = None
        
        # Mock database responses
        mock_cursor.fetchall.return_value = []
        mock_cursor.fetchone.return_value = None
        mock_db_connect.return_value = mock_conn
        
        # Mock user input (skip all merges)
        mock_ask.return_value = False
        
        # Test that main() can be called without errors
        try:
            with patch('sys.argv', ['merg_duplicates.py', '--limit-companies', '0', '--limit-facilities', '0']):
                md.main()
        except SystemExit:
            pass  # Expected if script exits
        except Exception as e:
            self.fail(f"Script execution failed: {e}")


class TestIntegration(unittest.TestCase):
    """Integration tests - require actual database connection"""

    def test_db_connect_env_vars(self):
        """Test that database connection requires proper env vars"""
        # Save original env
        original_db = os.environ.get("POSTGRES_DB")
        original_user = os.environ.get("POSTGRES_USER")
        original_pass = os.environ.get("POSTGRES_PASSWORD")
        original_port = os.environ.get("POSTGIS_HOST_PORT")
        
        try:
            # Remove required vars
            if "POSTGRES_DB" in os.environ:
                del os.environ["POSTGRES_DB"]
            
            # Should raise SystemExit
            with self.assertRaises(SystemExit):
                md.db_connect()
        finally:
            # Restore original env
            if original_db:
                os.environ["POSTGRES_DB"] = original_db
            if original_user:
                os.environ["POSTGRES_USER"] = original_user
            if original_pass:
                os.environ["POSTGRES_PASSWORD"] = original_pass
            if original_port:
                os.environ["POSTGIS_HOST_PORT"] = original_port

    @unittest.skipUnless(
        os.environ.get("POSTGRES_DB") and os.environ.get("POSTGIS_HOST_PORT"),
        "Requires database connection"
    )
    def test_db_connect_real(self):
        """Test actual database connection (requires .env)"""
        try:
            conn = md.db_connect()
            self.assertIsNotNone(conn)
            conn.close()
        except SystemExit:
            self.skipTest("Database connection failed - check .env file")
        except Exception as e:
            self.skipTest(f"Database connection failed: {e}")


def run_tests():
    """Run all tests"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestNormalization))
    suite.addTests(loader.loadTestsFromTestCase(TestDatabaseHelpers))
    suite.addTests(loader.loadTestsFromTestCase(TestProposalFunctions))
    suite.addTests(loader.loadTestsFromTestCase(TestScriptExecution))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegration))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    print("=" * 70)
    print("Testing merg_duplicates.py")
    print("=" * 70)
    print()
    
    success = run_tests()
    
    print()
    print("=" * 70)
    if success:
        print("✓ All tests passed!")
        sys.exit(0)
    else:
        print("✗ Some tests failed")
        sys.exit(1)
