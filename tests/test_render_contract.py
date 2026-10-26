import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class RenderContractTests(unittest.TestCase):
  def test_render_blueprint_security(self):
    text=(ROOT/'render.yaml').read_text()
    for expected in ['type: web','runtime: docker','plan: free','healthCheckPath: /healthz','key: EDGE_API_KEY','sync: false']:
      self.assertIn(expected,text)
    self.assertNotIn('value: secret',text)
  def test_docker_minimal_image(self):
    text=(ROOT/'Dockerfile').read_text()
    self.assertIn('requirements-rest.txt',text)
    self.assertNotIn('requirements-mcp.txt',text)
    self.assertIn('USER 65532',text)
    self.assertIn('uvicorn rest_api:app',text)
  def test_source_count(self):
    import json
    obj=json.loads((ROOT/'fixtures/morning_routine_188words.json').read_text())
    self.assertEqual((len(obj['paragraphs']),len(obj['sentences']),len(' '.join(obj['paragraphs']).split())),(6,22,188))
  def test_operator_live_opt_in(self):
    text=(ROOT/'smoke_test_render.py').read_text()
    self.assertIn('if not args.live:',text)
    self.assertIn('LIVE: NOT_PERFORMED',text)
  def test_mcp_not_exposed_in_web_entry(self):
    text=(ROOT/'Dockerfile').read_text()
    self.assertNotIn('mcp_oauth_server',text)

if __name__=='__main__':unittest.main()
