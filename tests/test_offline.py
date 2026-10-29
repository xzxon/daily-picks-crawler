import sys, unittest
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))
from selection import choose, filter_reason, safe_filename, author, is_r18
from crawler import historical_dates


def work(i, adult=False, period="recent", who=None, **extra):
    x={"id":i,"title":"主题/测试","user":{"name":who or f"作者{i}"},"tags":[],"total_bookmarks":1000,"total_view":5000,"page_count":1,"type":"illust","ai_type":0,"create_date":"2025-01-01T00:00:00+00:00","rank":i,"source_period":period,"is_r18":adult,"original_urls":[{"url":f"https://example.com/{i}.jpg","width":1600,"height":1600}]}
    x.update(extra); return x

class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.cfg={"daily_total":10,"normal_quota":7,"r18_quota":3,"recent_count":6,"historical_count":4,"min_bookmarks":0,"min_width":1200,"min_height":1200,"min_resolution":2_000_000,"aspect_ratio":[.45,2.2],"historical_min_year":2020,"excluded_tags":["manga","漫画"]}
    def test_filters(self):
        self.assertEqual(filter_reason(work(1,page_count=2),self.cfg),"multi_page")
        self.assertEqual(filter_reason(work(2,tags=["manga"]),self.cfg),"excluded_tag")
        self.assertEqual(filter_reason(work(3,ai_type=1),self.cfg),"ai")
        self.assertEqual(filter_reason(work(4,width=0,height=0,original_urls=[{"url":"x","width":100,"height":100}]),self.cfg),"low_resolution")
    def test_quota_author_and_filename(self):
        xs=[work(i,i<=3,"recent",f"u{i}") for i in range(1,4)] + [work(i,False,"historical",f"u{i}") for i in range(4,11)] + [work(i,True,"historical",f"u{i}") for i in range(11,15)]
        ys,_=choose(xs,self.cfg)
        self.assertEqual(len(ys),10); self.assertEqual(sum(is_r18(x) for x in ys),3)
        self.assertEqual(len({author(x) for x in ys}),10)
        self.assertIn("_",safe_filename(work(99),set()))
    def test_historical_dates(self):
        ds=historical_dates(10,date(2026,9,2),__import__('random').Random(1))
        self.assertEqual(len(ds),10); self.assertEqual(len(set(ds)),10); self.assertTrue(all(ds[i]>='2020-01-01' for i in range(10)))

if __name__ == '__main__': unittest.main()
