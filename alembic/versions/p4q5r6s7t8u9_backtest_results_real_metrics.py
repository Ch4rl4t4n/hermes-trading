"""Extend backtest_results for real metrics payload.

Revision ID: p4q5r6s7t8u9
Revises: q9w8e7r6t5y4
"""

from typing import Sequence, Union

from alembic import op

revision: str = "p4q5r6s7t8u9"
down_revision: Union[str, Sequence[str], None] = "q9w8e7r6t5y4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE backtest_results ADD COLUMN IF NOT EXISTS agent_id INTEGER")
    op.execute("ALTER TABLE backtest_results ADD COLUMN IF NOT EXISTS symbol VARCHAR(20)")
    op.execute("ALTER TABLE backtest_results ADD COLUMN IF NOT EXISTS strategy VARCHAR(50)")
    op.execute("ALTER TABLE backtest_results ADD COLUMN IF NOT EXISTS start_date DATE")
    op.execute("ALTER TABLE backtest_results ADD COLUMN IF NOT EXISTS end_date DATE")
    op.execute(
        "ALTER TABLE backtest_results ADD COLUMN IF NOT EXISTS initial_capital NUMERIC(12,2) DEFAULT 10000"
    )
    op.execute("ALTER TABLE backtest_results ADD COLUMN IF NOT EXISTS final_capital NUMERIC(12,2)")
    op.execute("ALTER TABLE backtest_results ADD COLUMN IF NOT EXISTS total_return NUMERIC(8,4)")
    op.execute("ALTER TABLE backtest_results ADD COLUMN IF NOT EXISTS max_drawdown NUMERIC(8,4)")
    op.execute("ALTER TABLE backtest_results ADD COLUMN IF NOT EXISTS win_rate NUMERIC(5,2)")
    op.execute("ALTER TABLE backtest_results ADD COLUMN IF NOT EXISTS total_trades INTEGER")
    op.execute("ALTER TABLE backtest_results ADD COLUMN IF NOT EXISTS winning_trades INTEGER")
    op.execute("ALTER TABLE backtest_results ADD COLUMN IF NOT EXISTS sharpe_ratio NUMERIC(6,3)")
    op.execute("ALTER TABLE backtest_results ADD COLUMN IF NOT EXISTS equity_curve JSONB")
    op.execute("ALTER TABLE backtest_results ADD COLUMN IF NOT EXISTS trades_log JSONB")
    op.execute("CREATE INDEX IF NOT EXISTS idx_backtest_user ON backtest_results(user_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_backtest_user")
    op.execute("ALTER TABLE backtest_results DROP COLUMN IF EXISTS trades_log")
    op.execute("ALTER TABLE backtest_results DROP COLUMN IF EXISTS equity_curve")
    op.execute("ALTER TABLE backtest_results DROP COLUMN IF EXISTS sharpe_ratio")
    op.execute("ALTER TABLE backtest_results DROP COLUMN IF EXISTS winning_trades")
    op.execute("ALTER TABLE backtest_results DROP COLUMN IF EXISTS total_trades")
    op.execute("ALTER TABLE backtest_results DROP COLUMN IF EXISTS win_rate")
    op.execute("ALTER TABLE backtest_results DROP COLUMN IF EXISTS max_drawdown")
    op.execute("ALTER TABLE backtest_results DROP COLUMN IF EXISTS total_return")
    op.execute("ALTER TABLE backtest_results DROP COLUMN IF EXISTS final_capital")
    op.execute("ALTER TABLE backtest_results DROP COLUMN IF EXISTS initial_capital")
    op.execute("ALTER TABLE backtest_results DROP COLUMN IF EXISTS end_date")
    op.execute("ALTER TABLE backtest_results DROP COLUMN IF EXISTS start_date")
    op.execute("ALTER TABLE backtest_results DROP COLUMN IF EXISTS strategy")
    op.execute("ALTER TABLE backtest_results DROP COLUMN IF EXISTS symbol")
    op.execute("ALTER TABLE backtest_results DROP COLUMN IF EXISTS agent_id")
