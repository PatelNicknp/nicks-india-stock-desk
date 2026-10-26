"""The rule that cuts a business summary to one plain line. No network."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

import company_lines as cl


def test_strips_legal_boilerplate_and_keeps_the_first_sentence():
    text = ("Bajaj Auto Limited, together with its subsidiaries, engages in the manufacture and sale of "
            "motorcycles and three-wheelers in India and internationally. It operates through Automotive, "
            "Investments, and Others segments. The company was founded in 1926.")
    assert cl.shorten(text, "Bajaj Auto Limited") == "Makes and sells motorcycles and three-wheelers in India and abroad."


def test_dots_in_ltd_do_not_end_the_sentence():
    text = "Foo Industries Ltd. manufactures steel pipes in India. It was founded in 1990."
    assert cl.shorten(text) == "Makes steel pipes in India."


def test_cut_at_about_twenty_words_on_a_word_boundary():
    text = ("Reliance Industries Limited engages in hydrocarbon exploration and production, petroleum refining and "
            "marketing, petrochemicals, advanced materials and composites, renewable, financial services, retail, "
            "and digital services worldwide.")
    line = cl.shorten(text, "Reliance Industries Limited")
    assert line.startswith("Works in hydrocarbon exploration and production")
    assert len(line.split()) <= 20
    assert line.endswith(".")
    assert "\u2014" not in line and "\u2013" not in line
    long_text = "Acme Limited provides " + " ".join("word%d" % i for i in range(40)) + "."
    cut = cl.shorten(long_text)
    assert len(cut.split()) <= 20
    assert cut.endswith("word18.")


def test_is_a_becomes_a_noun_phrase_and_dashes_go():
    text = "Cyient (formerly Infotech Enterprises Limited) is an Indian technology company \u2014 focused on engineering."
    assert cl.shorten(text) == "An Indian technology company, focused on engineering."


def test_empty_summary_gives_empty_line_and_fallback_is_never_blank():
    assert cl.shorten("") == ""
    assert cl.fallback_line("Auto Components", "Automobile") == "A company in Auto Components (Automobile sector)."
    assert cl.fallback_line("", "Financial Services") == "A company in the Financial Services sector."
    assert cl.fallback_line("", "", isin="INF204KB18R4").startswith("A fund")
    assert cl.fallback_line("", "", exchange="BSE") == "A company listed on BSE."


def test_build_lines_prefers_yahoo_then_profiles_then_industry():
    universe = pd.DataFrame([
        {"ticker": "AAA", "company": "AAA Ltd", "sector": "", "isin": "INE1", "exchange": "NSE"},
        {"ticker": "BBB", "company": "BBB Ltd", "sector": "", "isin": "INE2", "exchange": "NSE"},
        {"ticker": "CCC", "company": "CCC Ltd", "sector": "Chemicals", "isin": "INE3", "exchange": "BSE"},
    ])
    info = pd.DataFrame([
        {"ticker": "AAA", "company": "AAA Limited", "summary": "AAA Limited manufactures pumps in India.", "sector": "Industrials", "industry": "Pumps", "fetched_on": "2026-10-25"},
        {"ticker": "CCC", "company": "CCC Limited", "summary": "", "sector": "Basic Materials", "industry": "Specialty Chemicals", "fetched_on": "2026-10-25"},
    ])
    profiles = pd.DataFrame([
        {"ticker": "BBB", "summary": "BBB Ltd provides loans to small shops in India.", "sector": "", "industry": "", "source": "Screener About", "fetched_on": "2026-10-24"},
    ])
    out = cl.build_lines(universe, info, profiles, today="2026-10-25").set_index("ticker")
    assert out.loc["AAA", "line"] == "Makes pumps in India."
    assert out.loc["AAA", "source"] == "Yahoo"
    assert out.loc["BBB", "line"] == "Provides loans to small shops in India."
    assert out.loc["BBB", "source"] == "Screener About"
    assert out.loc["CCC", "line"] == "A company in Specialty Chemicals (Basic Materials sector)."
    assert out.loc["CCC", "source"] == "Industry fallback"
    assert (out["line"].str.len() > 0).all()


def test_screener_about_parser():
    page = ('<div class="company-profile"><div class="title">About</div>'
            '<div class="sub show-more-box about" style="flex-basis: 100px"><p>Widget Co. makes widgets.'
            '<sup><a href="x">[1]</a></sup></p></div></div>')
    assert cl.parse_screener_about(page) == "Widget Co. makes widgets."
    assert cl.parse_screener_about("<html></html>") == ""


def test_screener_style_incorporated_prefix_is_dropped():
    assert cl.shorten("Incorporated in 1984, Andhra Petrochemicals Ltd manufactures and sells Oxo Alcohols") == "Makes and sells Oxo Alcohols."
