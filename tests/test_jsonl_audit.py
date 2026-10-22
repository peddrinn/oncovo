import json
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'etl'))
from auditar_jsonl import audit, main

class AuditTests(unittest.TestCase):
    def test_valid_and_file_hash(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'x.jsonl'
            path.write_text('{"post_code":"AAAAAAAAAAA"}\n{"post_code":"BBBBBBBBBBB"}\n',encoding='utf-8')
            r=audit(path,'extraction')
            self.assertEqual(r['status'],'ok')
            self.assertEqual(r['valid_json_objects'],2)
            self.assertEqual(r['invalid_physical_lines'],0)
            self.assertEqual(len(r['sha256']),64)
            self.assertEqual(main(['--input',str(path),'--kind','extraction']),0)

    def test_broken_line_is_not_silently_repaired(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'broken.jsonl';p.write_text('{"post_code":"ABCDE12345", "caption":"a\nb"}\n')
            x=audit(p,'extraction')
            self.assertEqual(x['invalid_physical_lines'],2)
            self.assertEqual(x['status'],'invalid')
            self.assertEqual(main(['--input',str(p),'--kind','extraction']),2)

    def test_duplicate_keys_in_raw_are_informational_for_triage(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'duplicate.jsonl'
            p.write_text('{"code":"ABCDE12345"}\n{"code":"ABCDE12345"}\n')
            self.assertEqual(audit(p,'raw')['duplicate_valid_keys'],1)
            self.assertEqual(main(['--input',str(p),'--kind','raw']),0)
            self.assertEqual(main(['--input',str(p),'--kind','extraction']),3)

    def test_missing_codes_trigger_block(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'missing.jsonl';p.write_text('{"post_code":null}\n')
            self.assertEqual(audit(p,'editorial')['missing_keys'],1)

    def test_non_object_line_invalid(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'array.jsonl';p.write_text('[]\n')
            self.assertEqual(audit(p,'catalog')['status'],'invalid')

if __name__=='__main__':unittest.main()

# Teste separado para evitar regressão de leitura de U+2028 como \"nova linha\".
class UnicodeSeparatorsTests(unittest.TestCase):
    def test_unicode_line_separator_inside_caption_is_valid_jsonl(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'unicode.jsonl'
            payload={'code':'ABCDE12345','caption_text':'Texto um\u2028Texto dois'}
            path.write_text(json.dumps(payload,ensure_ascii=False)+'\n',encoding='utf-8')
            self.assertEqual(len(path.read_text().splitlines()),2)  # armadilha histórica
            result=audit(path,'raw')
            self.assertEqual(result['physical_lines'],1)
            self.assertEqual(result['valid_json_objects'],1)
            self.assertEqual(result['status'],'ok')
