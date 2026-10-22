import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'etl'))
from validacao_extracao import validate
from criar_revisao import make_review
from extrair_llm import messages_for,parse_text,PROMPT
from instagram_collect import serialize
from triagem_avancada import classify_and_score


class OldPipelineTests(unittest.TestCase):
    def test_prompt_versioned_from_legacy(self):
        prompt=PROMPT.read_text(encoding='utf8')
        self.assertIn('commercial_offer_hours_not_opening_hours',prompt)
        self.assertIn('ticket_required',prompt)
        self.assertIn('metadata.location_name',prompt)
        msg=messages_for({'post_code':'ABCDEFGHIJK','caption_text_clean':'Restaurante X em BH','taken_at':'2026-10-21T12:00:00Z'})
        self.assertEqual(len(msg),2)
        self.assertNotIn('"post_url"',msg[1]['content'])
        self.assertIn('Restaurante X',msg[1]['content'])
    def test_boolean_conflict_requires_review(self):
        payload={'extraction_status':'ok','content_type':'event','main_entity':{},'event':{},
            'location':{},'commercial_info':{'is_free':True,'ticket_required':True},
            'classification':{},'quality':{'confidence_overall':.94,'risk_flags':[]}}
        x=validate(payload)
        self.assertEqual(x['extraction_status'],'partial')
        self.assertLessEqual(x['quality']['confidence_overall'],.74)
        self.assertIn('free_and_ticket_required_conflict',x['quality']['risk_flags'])
    def test_review_not_automatically_published(self):
        obj={'post_code':'ABCDEFGHIJK','content_type':'place','main_entity':{'name':'Bar de teste'},
          'event':{},'location':{},'classification':{'category':'bar'},
          'commercial_info':{},'quality':{'risk_flags':[]}}
        with tempfile.TemporaryDirectory() as d:
            input_file=Path(d)/'in.jsonl';output_file=Path(d)/'review.jsonl'
            input_file.write_text(json.dumps(obj)+'\n')
            self.assertEqual(make_review(input_file,output_file),1)
            self.assertEqual(json.loads(output_file.read_text())['publish_status'],'review')
    def test_stale_data_does_not_auto_publish(self):
        from preparar_publicacao import transform
        approved={'post_code':'ABCDEFGHIJK','content_type':'place','publish_status':'published','display_title':'Bar X'}
        ext={'post_code':'ABCDEFGHIJK','extraction_status':'partial','content_type':'place',
             'main_entity':{'name':'Bar X'},'location':{'city':'Belo Horizonte','venue_name':'Bar X'},
             'event':{},'commercial_info':{},'classification':{'category':'bar'},
             'quality':{'confidence_overall':.8,'risk_flags':[]}}
        self.assertEqual(transform(approved,ext)[1],'review')
    def test_legacy_scoring(self):
        post={'caption_text_clean':'Show de jazz ao vivo em BH nesta sexta! Rua X, às 20h, evento cultural.',
              'source_profile':'vamobh','taken_at':'2026-10-21T00:00:00Z',
              'location_address':'Rua X','has_specific_location':True,'caption_duplicate':False,
              'location_is_generic':False,'mentions':[],'coauthors':[]}
        klass,score,queue,_=classify_and_score(post)
        self.assertIn(klass,('candidato_evento','candidato_lugar'))
        self.assertGreater(score,0)
    def test_serializer_v2(self):
        class Obj:
            def model_dump(self,mode):return {'code':'ABCDEFGHIJK'}
        self.assertEqual(serialize(Obj())['code'],'ABCDEFGHIJK')

if __name__=='__main__':unittest.main()
