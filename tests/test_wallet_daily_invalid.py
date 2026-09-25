import unittest
from aoa.seed import SeedBook,DAY_US

class WalletInvalidDayTests(unittest.TestCase):
    def row(self,day):
        return dict(source='S',row_key=str(day),day=day,wallet_btc=100,amount_btc=1,account='S',kind='realisedpnl',ordinal=day,quality='date_only_ledger')
    def test_rejected_same_day_row_invalidates_close(self):
        b={'source':'S','day':1,'account':'S','reason':'잔고 행 검증 거부: conflicting ID'}
        book=SeedBook(blocks=[b],daily=[self.row(1),self.row(2)])
        self.assertIsNone(book.at(2*DAY_US)['btc'])
        self.assertEqual(book.at(3*DAY_US)['btc'],100)
    def test_unreconciled_cashflow_must_not_disappear_at_midnight(self):
        b={'source':'S','day':1,'account':'S','reason':'입출금 시각이 날짜까지만 있음'}
        self.assertIsNone(SeedBook(blocks=[b],daily=[self.row(1)]).at(2*DAY_US)['btc'])
    def test_complete_ledger_cashflow_is_usable_after_day_ends(self):
        b={'source':'S','day':1,'account':'S','reason':'DAILY_RECONCILED_CASHFLOW: date only'}
        book=SeedBook(blocks=[b],daily=[self.row(0),self.row(1)])
        self.assertIsNone(book.at(DAY_US+1)['btc'])
        self.assertEqual(book.at(2*DAY_US)['btc'],100)
