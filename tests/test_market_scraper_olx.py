import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scrapers"))

import market_scraper


class OlxCardParserTest(unittest.TestCase):
    def test_parses_price_size_neighborhood_and_rooms(self):
        text = "Двустаен апартамент\n247 071 €\n150 кв.м\nгр. София, Лозенец - 25 септември"

        listing = market_scraper.parse_olx_card_text(text, "София")

        self.assertIsNotNone(listing)
        self.assertEqual(listing.city, "София")
        self.assertEqual(listing.source, "olx.bg")
        self.assertEqual(listing.size_sqm, 150)
        self.assertEqual(listing.price_eur, 247071)
        self.assertEqual(listing.rooms, 2)
        self.assertIn("лозенец", listing.neighborhood)

    def test_rejects_rental_sized_price(self):
        text = "Двустаен апартамент под наем\n700 €\n65 кв.м\nгр. София, Център - днес"

        listing = market_scraper.parse_olx_card_text(text, "София")

        self.assertIsNone(listing)

    def test_rejects_missing_size(self):
        text = "Апартамент\n120 000 €\nгр. Пловдив, Кършияка - днес"

        listing = market_scraper.parse_olx_card_text(text, "Пловдив")

        self.assertIsNone(listing)


if __name__ == "__main__":
    unittest.main()
