"""Regressões A2 sem rede, scraping, Docker, nem dependências externas."""
import csv
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'etl'))
from resolver_entidades import resolve, main, strong_signature, location_details

NOW = datetime(2026,10,22,12,0,tzinfo=ZoneInfo('America/Sao_Paulo'))


def place(code, name='Café Horizonte', address='Rua Bahia, 123', bairro='Centro', status='published',score=90):
    return {'id':('id_'+code), 'source_id':code, 'source_url':f'https://www.instagram.com/p/{code}/',
            'type':'place','status':status,'title':name,'city':'Belo Horizonte',
            'address':address,'neighborhood':bairro,'description':'Café, brunch',
            'search_text':'cafe brunch', 'rank_score_base':score,
            'source_label':'@perfil', 'starts_at':None,'ends_at':None}


def event(code, title='Samba no Centro', start='2026-10-25T19:00:00-03:00',end='2026-10-25T23:00:00-03:00',address='Rua Bahia, 123'):
    row=place(code,name=title,address=address)
    row.update(type='event',starts_at=start,ends_at=end)
    return row


class ResolutionTests(unittest.TestCase):
    def test_one_place_two_posts_only_one_card(self):
        result=resolve([place('POSTAAAAAA1'),place('POSTAAAAAA2',score=91)],now=NOW)
        self.assertEqual(len(result['catalog']),1)
        self.assertEqual(result['report']['sources_collapsed'],1)
        self.assertEqual(len(result['source_map']),2)
        self.assertEqual(sum(r['is_primary'] for r in result['source_map']),1)
        self.assertEqual(result['catalog'][0]['source_id'],'POSTAAAAAA2')
        self.assertEqual(result['catalog'][0]['id'],'id_POSTAAAAAA1')

    def test_branches_not_merged(self):
        rows=[place('POSTAAAAAA1'),place('POSTAAAAAA2',address='Rua Bahia, 222')]
        self.assertEqual(len(resolve(rows,now=NOW)['catalog']),2)

    def test_branches_differ_by_unit_suite(self):
        a=place('POSTAAAAAA1',address='Rua Bahia, 123, loja 1')
        b=place('POSTAAAAAA2',address='Rua Bahia, 123, loja 2')
        self.assertEqual(len(resolve([a,b],now=NOW)['catalog']),2)

    def test_similar_name_without_address_does_not_auto_merge(self):
        rows=[place('POSTAAAAAA1',address=''),place('POSTAAAAAA2',address='')]
        r=resolve(rows,now=NOW)
        self.assertEqual(len(r['catalog']),2)
        self.assertEqual(len(r['candidates']),1)
        self.assertEqual(r['candidates'][0]['decision'],'pending_review')

    def test_name_only_never_merges(self):
        rows=[place('POSTAAAAAA1',address=''),place('POSTAAAAAA2',address='',bairro='Savassi')]
        self.assertEqual(len(resolve(rows,now=NOW)['catalog']),2)

    def test_brand_rename_requires_review(self):
        rows=[place('POSTAAAAAA1','Café Horizonte'),place('POSTAAAAAA2','Café Horizonte Novo')]
        self.assertEqual(len(resolve(rows,now=NOW)['catalog']),2)

    def test_manual_override_requires_evidence(self):
        rows=[place('POSTAAAAAA1',address=''),place('POSTAAAAAA2',address='')]
        cfg={'version':1,'approved_groups':[{'type':'place','sources':['instagram:POSTAAAAAA1','instagram:POSTAAAAAA2'],
             'reason':'Mesma fachada validada','reviewed_by':'editor','reviewed_at':'2026-10-22'}], 'rejected_pairs':[]}
        r=resolve(rows,overrides=cfg,now=NOW)
        self.assertEqual(len(r['catalog']),1)

    def test_manual_override_without_reviewer_is_rejected(self):
        rows=[place('POSTAAAAAA1'),place('POSTAAAAAA2')]
        cfg={'version':1,'approved_groups':[{'type':'place','sources':['instagram:POSTAAAAAA1','instagram:POSTAAAAAA2'],
             'reason':'Verificado'}],'rejected_pairs':[]}
        with self.assertRaisesRegex(ValueError,'revisor'):resolve(rows,overrides=cfg,now=NOW)

    def test_explicit_rejection_prevents_auto_merge(self):
        rows=[place('POSTAAAAAA1'),place('POSTAAAAAA2')]
        cfg={'version':1,'approved_groups':[], 'rejected_pairs':[
            {'type':'place','sources':['instagram:POSTAAAAAA1','instagram:POSTAAAAAA2'],'reason':'Unidades diferentes'}]}
        r=resolve(rows,overrides=cfg,now=NOW)
        self.assertEqual(len(r['catalog']),2)
        self.assertEqual(r['report']['rejected_auto_pairs'],1)
        self.assertEqual(r['candidates'][0]['decision'],'rejected')

    def test_event_occurrences_remain_separate(self):
        a=event('POSTAAAAAA1')
        b=event('POSTAAAAAA2',start='2026-10-26T19:00:00-03:00',end='2026-10-26T23:00:00-03:00')
        self.assertEqual(len(resolve([a,b],now=NOW)['catalog']),2)

    def test_same_event_same_occurrence_merges(self):
        r=resolve([event('POSTAAAAAA1'),event('POSTAAAAAA2')],now=NOW)
        self.assertEqual(r['report']['events'],1)
        self.assertEqual(r['report']['sources_collapsed'],1)

    def test_event_different_end_does_not_merge(self):
        rows=[event('POSTAAAAAA1'),event('POSTAAAAAA2',end='2026-10-25T22:00:00-03:00')]
        self.assertEqual(len(resolve(rows,now=NOW)['catalog']),2)

    def test_old_events_promotion_and_unapproved_blocked(self):
        past=event('POSTAAAAAA1',start='2026-10-10T19:00:00-03:00',end='2026-10-10T23:00:00-03:00')
        review=place('POSTAAAAAA2',status='review')
        promo=place('POSTAAAAAA3');promo['type']='promotion'
        r=resolve([past,review,promo],now=NOW)
        self.assertEqual(r['catalog'],[])
        self.assertEqual(sum(r['report']['withheld'].values()),3)

    def test_bad_event_date_cannot_reappear(self):
        e=event('POSTAAAAAA1');e['ends_at']='ontem'
        self.assertEqual(resolve([e],now=NOW)['catalog'],[])

    def test_double_input_rejected_not_silently_dropped(self):
        a=place('POSTAAAAAA1')
        with self.assertRaisesRegex(ValueError,'repetida'):resolve([a,a],now=NOW)

    def test_data_is_order_independent(self):
        rows=[place('POSTAAAAAA1'),place('POSTAAAAAA2'),place('POSTAAAAAA3',address='Rua Bahia, 555')]
        a=resolve(rows,now=NOW);b=resolve(list(reversed(rows)),now=NOW)
        self.assertEqual(a,b)

    def test_registry_keeps_existing_id_even_if_earlier_code_arrives(self):
        first=resolve([place('ZZZZZZZZZZ1')],now=NOW)
        old_id=first['catalog'][0]['id']
        another=place('AAAAAAAAAA1',score=98)
        second=resolve([another,place('ZZZZZZZZZZ1')],registry=first['registry'],now=NOW)
        self.assertEqual(second['catalog'][0]['id'],old_id)
        self.assertEqual(second['catalog'][0]['source_id'],'AAAAAAAAAA1')

    def test_registry_incremental_partial_retains_absent(self):
        a=resolve([place('POSTAAAAAA1'),place('POSTAAAAAA2',address='Rua Bahia, 222')],now=NOW)
        b=resolve([place('POSTAAAAAA1')],registry=a['registry'],now=NOW)
        self.assertEqual(len(b['registry']['sources']),2)

    def test_contradictory_registry_blocks_unsafe_merge(self):
        first=resolve([place('POSTAAAAAA1',address=''),place('POSTAAAAAA2',address='')],now=NOW)
        with self.assertRaisesRegex(ValueError,'IDs diferentes'):
            resolve([place('POSTAAAAAA1'),place('POSTAAAAAA2')],registry=first['registry'],now=NOW)

    def test_cli_writes_preview_and_never_touches_input(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.jsonl'
            rows=[place('POSTAAAAAA1'),place('POSTAAAAAA2')]
            raw='\n'.join(json.dumps(r) for r in rows)+'\n'
            source.write_text(raw,encoding='utf-8')
            self.assertEqual(main(['--input',str(source),'--outdir',str(root/'out')]),0)
            out=root/'out'
            self.assertEqual(len((out/'search_items_canonical.jsonl').read_text().splitlines()),1)
            with (out/'source_entity_map.csv').open() as f:
                self.assertEqual(len(list(csv.DictReader(f))),2)
            self.assertTrue((out/'entity_registry.proposed.json').exists())
            self.assertEqual(source.read_text(),raw)


    def test_manual_override_cannot_merge_different_event_occurrences(self):
        cfg={'version':1,'approved_groups':[{'type':'event',
            'sources':['instagram:POSTAAAAAA1','instagram:POSTAAAAAA2'],
            'reason':'Mesmo nome','reviewed_by':'editor','reviewed_at':'2026-10-22'}],
            'rejected_pairs':[]}
        rows=[event('POSTAAAAAA1'),event('POSTAAAAAA2',
            start='2026-10-26T19:00:00-03:00',end='2026-10-26T23:00:00-03:00')]
        with self.assertRaisesRegex(ValueError,'Ocorrências'):
            resolve(rows,overrides=cfg,now=NOW)

    def test_name_same_city_no_neighborhood_still_candidate(self):
        rows=[place('POSTAAAAAA1',address='',bairro=''),place('POSTAAAAAA2',address='',bairro='')]
        r=resolve(rows,now=NOW)
        self.assertEqual(len(r['catalog']),2)
        self.assertEqual(len(r['candidates']),1)

    def test_out_of_scope_city_withheld(self):
        obj=place('POSTAAAAAA1');obj['city']='Contagem'
        r=resolve([obj],now=NOW)
        self.assertEqual(r['catalog'],[])
        self.assertEqual(r['report']['withheld']['outside_scope'],1)

    def test_partial_manual_group_inherits_pinned_card_id(self):
        initial=resolve([place('ZZZZZZZZZZ1')],now=NOW)
        override={'version':1,'approved_groups':[{'type':'place',
            'sources':['instagram:ZZZZZZZZZZ1','instagram:AAAAAAAAAA1'],
            'reason':'Revisão de identidade','reviewed_by':'editor','reviewed_at':'2026-10-22'}],
            'rejected_pairs':[]}
        newer=place('AAAAAAAAAA1',address='')
        newer['title']='Novo nome'
        r=resolve([newer],registry=initial['registry'],overrides=override,now=NOW)
        self.assertEqual(r['catalog'][0]['id'],initial['catalog'][0]['id'])
        self.assertEqual(r['source_map'][0]['entity_id'],initial['source_map'][0]['entity_id'])

if __name__=='__main__': unittest.main()
