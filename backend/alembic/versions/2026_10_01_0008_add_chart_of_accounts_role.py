"""Add role column to chart_of_accounts and backfill roles for GST/accounting parity

Revision ID: 0008_add_coa_role
Revises: 0007_add_accounting_periods
Create Date: 2026-10-01 00:00:00 UTC
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0008_add_coa_role"
down_revision = "0007_add_accounting_periods"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add additive nullable column 'role'
    op.add_column("chart_of_accounts", sa.Column("role", sa.String(50), nullable=True))
    op.create_index("ix_coa_role", "chart_of_accounts", ["role"])

    # 2. Backfill roles based on code + name for both legacy and new charts
    # Output GST
    op.execute("""
        UPDATE chart_of_accounts
        SET role = 'OUTPUT_CGST'
        WHERE LOWER(account_name) LIKE '%output%cgst%'
           OR (account_code IN ('2110', '2020') AND LOWER(account_name) LIKE '%cgst%')
    """)
    op.execute("""
        UPDATE chart_of_accounts
        SET role = 'OUTPUT_SGST'
        WHERE LOWER(account_name) LIKE '%output%sgst%'
           OR (account_code IN ('2120', '2030') AND LOWER(account_name) LIKE '%sgst%')
    """)
    op.execute("""
        UPDATE chart_of_accounts
        SET role = 'OUTPUT_IGST'
        WHERE LOWER(account_name) LIKE '%output%igst%'
           OR (account_code IN ('2130', '2040') AND LOWER(account_name) LIKE '%igst%')
    """)
    op.execute("""
        UPDATE chart_of_accounts
        SET role = 'OUTPUT_CESS'
        WHERE LOWER(account_name) LIKE '%output%cess%'
           OR (account_code = '2140' AND LOWER(account_name) LIKE '%cess%')
    """)

    # Input GST
    op.execute("""
        UPDATE chart_of_accounts
        SET role = 'INPUT_CGST'
        WHERE LOWER(account_name) LIKE '%input%cgst%'
           OR (account_code IN ('1210', '1060') AND LOWER(account_name) LIKE '%cgst%')
    """)
    op.execute("""
        UPDATE chart_of_accounts
        SET role = 'INPUT_SGST'
        WHERE LOWER(account_name) LIKE '%input%sgst%'
           OR (account_code IN ('1220', '1070') AND LOWER(account_name) LIKE '%sgst%')
    """)
    op.execute("""
        UPDATE chart_of_accounts
        SET role = 'INPUT_IGST'
        WHERE LOWER(account_name) LIKE '%input%igst%'
           OR (account_code IN ('1230', '1080') AND LOWER(account_name) LIKE '%igst%')
    """)
    op.execute("""
        UPDATE chart_of_accounts
        SET role = 'INPUT_CESS'
        WHERE LOWER(account_name) LIKE '%input%cess%'
           OR (account_code = '1240' AND LOWER(account_name) LIKE '%cess%')
    """)

    # Sales Return vs Sales (Resolves 4020 collision: name+role)
    op.execute("""
        UPDATE chart_of_accounts
        SET role = 'SALES_RETURN'
        WHERE LOWER(account_name) LIKE '%sales return%'
           OR LOWER(account_name) LIKE '%sale return%'
           OR (account_code = '4030' AND LOWER(account_name) LIKE '%return%')
    """)
    op.execute("""
        UPDATE chart_of_accounts
        SET role = 'SALES'
        WHERE (LOWER(account_name) LIKE '%sales%' OR LOWER(account_name) LIKE '%sale%')
          AND role IS NULL
    """)

    # Purchase & Purchase Return
    op.execute("""
        UPDATE chart_of_accounts
        SET role = 'PURCHASE_RETURN'
        WHERE LOWER(account_name) LIKE '%purchase return%'
           OR account_code = '5020'
    """)
    op.execute("""
        UPDATE chart_of_accounts
        SET role = 'PURCHASE'
        WHERE (LOWER(account_name) LIKE '%purchase%' OR LOWER(account_name) LIKE '%direct expenses%')
          AND role IS NULL
    """)

    # Debtors & Creditors
    op.execute("""
        UPDATE chart_of_accounts
        SET role = 'DEBTORS'
        WHERE (LOWER(account_name) LIKE '%debtor%'
           OR LOWER(account_name) LIKE '%receivable%'
           OR (account_code IN ('1100', '1010') AND (LOWER(account_name) LIKE '%trade%' OR LOWER(account_name) LIKE '%debtor%')))
    """)
    op.execute("""
        UPDATE chart_of_accounts
        SET role = 'CREDITORS'
        WHERE (LOWER(account_name) LIKE '%creditor%'
           OR LOWER(account_name) LIKE '%trade payable%'
           OR account_code = '2010')
          AND LOWER(account_name) NOT LIKE '%tds%'
    """)

    # Other Operating Income
    op.execute("""
        UPDATE chart_of_accounts
        SET role = 'OTHER_INCOME'
        WHERE (LOWER(account_name) LIKE '%other%income%' OR LOWER(account_name) LIKE '%operating income%' OR account_code = '4030')
          AND role IS NULL
    """)


def downgrade() -> None:
    op.drop_index("ix_coa_role", table_name="chart_of_accounts")
    op.drop_column("chart_of_accounts", "role")
