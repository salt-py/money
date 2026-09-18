"""One-off script to (re)generate the synthetic fixture PDFs under
tests/fixtures/ -- fake bank statements with made-up numbers, used to test
pdf_import.py without ever touching a real statement. Not run automatically
by pytest; re-run manually if a fixture needs to change:

    python tests/fixtures/generate_synthetic_pdf.py
"""

from pathlib import Path

from fpdf import FPDF

FIXTURES_DIR = Path(__file__).parent

# Mimics NatWest's "Transactions" PDF export: plain whitespace-aligned text,
# no drawn table borders, one transaction per line.
NATWEST_LINES = [
    "Transactions-01",
    "FAKE T E",
    "Select Account",
    "Account details",
    "*****000 . 00-00-00",
    "From",
    "01/08/2026",
    "To",
    "31/08/2026",
    "Date of creation",
    "01/09/2026",
    "",
    "Your transactions",
    "Date Description Type Paid in (£) Paid out (£)",
    "03 Aug TESCO STORES 1234 Debit Card Transaction -£32.10",
    "02 Aug ACME EXAMPLE LTD Automated Credit £2,500.00",
    "01 Aug EXAMPLE KIDS CLUB Mobile/Online Transaction -£800.00",
]


def generate_natwest():
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    for line in NATWEST_LINES:
        pdf.cell(0, 6, line, ln=1)
    out_path = FIXTURES_DIR / "synthetic_natwest_statement.pdf"
    pdf.output(str(out_path))
    print(f"Wrote {out_path}")


# Mimics a Santander credit card statement: a real drawn table, ordinal
# dates with no year, some rows with no date at all, and a couple of
# summary rows that must be filtered out by description pattern.
SANTANDER_HEADER_LINES = [
    "Account summary as at: 11th September 2026 for card number ending 0000",
    "Previous balance as at 13th August 2026: £1,000.00",
    "Your new balance: £930.60",
]
SANTANDER_TABLE = [
    ["Date", "Description", "Amount (£)"],
    ["", "Balance brought forward from previous statement", "1,000.00"],
    ["01st Aug", "FAKE SHOP LTD", "25.50"],
    ["05th Aug", "Cash Transaction Fee", "3.00"],
    ["", "Balance 900.00 Interest 0.000% to 01-01-2030", ""],
    ["", "Interest", "2.10"],
    ["", "Total of New Transactions:", "30.60"],
]
SANTANDER_COL_WIDTHS = [25, 130, 25]


def generate_santander():
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    for line in SANTANDER_HEADER_LINES:
        pdf.cell(0, 6, line, ln=1)
    pdf.ln(4)
    for row in SANTANDER_TABLE:
        for text, width in zip(row, SANTANDER_COL_WIDTHS):
            pdf.cell(width, 8, text, border=1)
        pdf.ln(8)
    out_path = FIXTURES_DIR / "synthetic_santander_statement.pdf"
    pdf.output(str(out_path))
    print(f"Wrote {out_path}")


# Mimics a NatWest credit card statement: plain text, two leading "DD MON"
# dates per transaction line, a trailing "-" (no space) marking a credit,
# and jammed-together digit+letter dates ("03SEP" not "03 SEP") -- a real
# font-kerning quirk seen on the actual statement this was modelled on.
NATWEST_CC_LINES = [
    "1of2",
    "MRFAKEPERSON",
    "10August -09September 2026",
    "Trans Post",
    "Date Date Description Amount",
    "BALANCE FROMPREVIOUS STATEMENT £100.00",
    "03SEP 03SEP DIRECTDEBITPAYMENT 100.00-",
    "Sub-Total 0.00",
    "Trans Post",
    "Date Date Description Amount",
    "03SEP 04SEP FAKESHOPLTD 10.99",
    "06SEP 07SEP FAKEOVERSEASLTD 20.93",
    "28.22 USD PAYMENTSCHEMEEXCHANGERATE 1.348304",
    "07SEP 07SEP NON-STERLINGTRANSACTIONFEE 0.58",
    "Sub-Total 32.50",
    "NEWBALANCE £32.50",
    "New Balance = £32.50",
]


def generate_natwest_credit_card():
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    for line in NATWEST_CC_LINES:
        pdf.cell(0, 6, line, ln=1)
    out_path = FIXTURES_DIR / "synthetic_natwest_credit_card_statement.pdf"
    pdf.output(str(out_path))
    print(f"Wrote {out_path}")


# Mimics a Capital One statement: plain text with two unsigned amount
# columns placed side by side ("Paid in" / "Paid out", no borders) --
# which column a given amount is in can only be told from its horizontal
# position, not from the flattened text alone.
CAPITAL_ONE_HEADER = ["Statement date 10 September 26", "Your new balance £4,000.00"]
CAPITAL_ONE_ROWS = [
    ["", "Your transaction details", "Paid in", "Paid out"],
    ["16 Aug", "FAKE SHOP LTD", "", "63.99"],
    ["02 Sep", "Direct Debit Payment - Thank You", "244.60", ""],
    ["10 Sep", "STATEMENT TOTALS", "244.60", "63.99"],
]
CAPITAL_ONE_COL_WIDTHS = [20, 100, 35, 35]


def generate_capital_one():
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    for line in CAPITAL_ONE_HEADER:
        pdf.cell(0, 6, line, ln=1)
    pdf.ln(4)
    for row in CAPITAL_ONE_ROWS:
        for text, width in zip(row, CAPITAL_ONE_COL_WIDTHS):
            pdf.cell(width, 8, text, border=0)
        pdf.ln(8)
    out_path = FIXTURES_DIR / "synthetic_capital_one_statement.pdf"
    pdf.output(str(out_path))
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    generate_natwest()
    generate_santander()
    generate_natwest_credit_card()
    generate_capital_one()
