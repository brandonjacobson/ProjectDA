"""Terminal dashboard — live P&L, positions, win rate printed every 60s."""
import asyncio
import logging
import time
from typing import TYPE_CHECKING

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.columns import Columns
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

if TYPE_CHECKING:
    from src.execution.order_manager import OrderManager
    from src.risk.risk_engine import RiskEngine

logger = logging.getLogger(__name__)
console = Console() if RICH_AVAILABLE else None


class Dashboard:
    """Prints live trading status to terminal every `refresh_secs` seconds."""

    def __init__(
        self,
        order_manager: "OrderManager",
        risk_engine: "RiskEngine",
        refresh_secs: int = 60,
        paper_mode: bool = True,
    ):
        self.order_manager = order_manager
        self.risk_engine = risk_engine
        self.refresh_secs = refresh_secs
        self.paper_mode = paper_mode
        self._running = False

    async def run(self) -> None:
        self._running = True
        while self._running:
            try:
                self._render()
            except Exception as e:
                logger.error(f"Dashboard render error: {e}")
            await asyncio.sleep(self.refresh_secs)

    def stop(self) -> None:
        self._running = False

    def _render(self) -> None:
        om = self.order_manager
        re = self.risk_engine
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        mode = "[bold yellow]PAPER[/bold yellow]" if self.paper_mode else "[bold red]LIVE[/bold red]"

        if RICH_AVAILABLE and console:
            self._render_rich(om, re, now, mode)
        else:
            self._render_plain(om, re, now)

    def _render_rich(self, om, re, now: str, mode: str) -> None:
        # Summary panel
        status = "[red]KILL SWITCH[/red]" if re.kill_switch_active else (
            "[yellow]CIRCUIT BREAK[/yellow]" if re.is_circuit_breaker_active() else "[green]ACTIVE[/green]"
        )
        summary = (
            f"Mode: {mode}  |  Status: {status}\n"
            f"Time: {now}\n"
            f"Total PnL: [{'green' if om.total_pnl >= 0 else 'red'}]${om.total_pnl:+.2f}[/]\n"
            f"Daily PnL: [{'green' if om.daily_pnl >= 0 else 'red'}]${om.daily_pnl:+.2f}[/]\n"
            f"Win Rate:  {om.win_rate:.1%} ({len(om.closed_positions)} closed)\n"
            f"Portfolio: ${re.portfolio_size:.0f}  Max pos: ${re.max_position_size:.0f}"
        )
        console.print(Panel(summary, title="[bold]ProjectDA — Polymarket Bot[/bold]", border_style="blue"))

        # Open positions table
        if om.open_positions:
            table = Table(title="Open Positions", box=box.SIMPLE_HEAVY)
            table.add_column("Symbol", style="cyan")
            table.add_column("Dir")
            table.add_column("Size", justify="right")
            table.add_column("Entry", justify="right")
            table.add_column("Current", justify="right")
            table.add_column("PnL", justify="right")
            for pos in om.open_positions:
                pnl_color = "green" if pos.pnl >= 0 else "red"
                table.add_row(
                    pos.symbol,
                    pos.direction.upper(),
                    f"${pos.size:.2f}",
                    f"{pos.entry_price:.4f}",
                    f"{pos.current_price:.4f}",
                    f"[{pnl_color}]${pos.pnl:+.2f}[/]",
                )
            console.print(table)
        else:
            console.print("[dim]No open positions[/dim]")
        console.print()

    def _render_plain(self, om, re, now: str) -> None:
        mode = "PAPER" if self.paper_mode else "LIVE"
        status = "KILL" if re.kill_switch_active else ("CBRKR" if re.is_circuit_breaker_active() else "ACTIVE")
        print(f"\n{'='*60}")
        print(f"ProjectDA [{mode}] | {now} | {status}")
        print(f"Total PnL: ${om.total_pnl:+.2f} | Daily: ${om.daily_pnl:+.2f} | Win: {om.win_rate:.1%}")
        print(f"Open: {len(om.open_positions)} | Closed: {len(om.closed_positions)}")
        for pos in om.open_positions:
            print(f"  {pos.symbol} {pos.direction.upper()} ${pos.size:.2f} @ {pos.entry_price:.4f} → {pos.current_price:.4f} PnL=${pos.pnl:+.2f}")
        print(f"{'='*60}\n")
