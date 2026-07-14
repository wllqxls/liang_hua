# Existing Strategy Failure Baseline

The existing active signal modes are frozen as a failure baseline before
`PULLBACK_CONFIRMATION` research begins. They are not candidates for further
parameter tuning.

| Source | SHA-256 | Recorded conclusion |
|---|---|---|
| `docs/strategy-validation.md` | `A3CA72FF55B4B9B3DFF5913D012D0F8F42F8AD1FF40425A3F793300A57F311AE` | All active modes failed the 365-day gate. |
| `docs/strategy-diagnostics.md` | `6F83B3AC0A4E28CDBD8D5CB27C12594263D7D0CA2873AD734807DCA2BFC4BA48` | `KEY_LEVEL` lost before fees; costs then amplified the loss. `KEY_LEVEL_RSI` behaved as a union, not a confirmation. |

This record freezes the interpretation, not the data: a later report may be
generated only by the validation scripts and must state a new data end time.
