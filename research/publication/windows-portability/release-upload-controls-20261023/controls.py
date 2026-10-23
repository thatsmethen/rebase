import importlib.util,pathlib,tempfile,json,os,hashlib,zipfile,shutil,sys
p=pathlib.Path(sys.argv[1] if len(sys.argv)>1 else '.github/scripts/upload-windows-preview.py')
spec=importlib.util.spec_from_file_location('upload',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
checks=0
def check(value):
 global checks
 assert value;checks+=1
def refused(fn):
 global checks
 try:fn()
 except m.Refused:checks+=1
 else:raise AssertionError('Expected refusal')
v=m.inputs({'RUN_ID':'39949650116','SOURCE_COMMIT':'8c6ec4b8a41f31ec0472a3cbeaa3d6c652a9474e','EXPECTED_SHA256':'f699f506e5bcf3b10a82ae8cd71c0efea3f56c44b2726065771512cad42586d2','RELEASE_TAG':'v0.21.1-windows-preview.2','ASSET_NAME':'Rebase-0.21.1-windows-preview.2-x64.zip','GITHUB_REPOSITORY':'thatsmethen/rebase'})
check(len(v)==6)
for key,value in [('RUN_ID','1;echo token'),('RUN_ID','0'),('SOURCE_COMMIT','a'*39),('SOURCE_COMMIT','a'*41),('EXPECTED_SHA256','g'*64),('RELEASE_TAG','--clobber'),('RELEASE_TAG','../tag'),('RELEASE_TAG','v1\n'),('ASSET_NAME','../name.zip'),('ASSET_NAME','payload.zip#label'),('ASSET_NAME','payload.exe'),('ASSET_NAME','a.zip\n'),('GITHUB_REPOSITORY','owner/repo/other')]:
 refused(lambda key=key,value=value:m.inputs(dict(v,**{key:value})))
run={'id':39949650116,'status':'completed','conclusion':'success','head_sha':v['SOURCE_COMMIT'],'path':'.github/workflows/windows-application.yml'}
m.verify_run(run,v);checks+=1
for key,value in [('id',1),('status','in_progress'),('conclusion','failure'),('head_sha','f'*40),('path','.github/workflows/unreviewed.yml')]:refused(lambda key=key,value=value:m.verify_run(dict(run,**{key:value}),v))
release={'id':421801975,'tag_name':v['RELEASE_TAG'],'draft':True,'prerelease':True,'target_commitish':v['SOURCE_COMMIT']}
m.verify_release(release,v);checks+=1
for key,value in [('id',True),('draft',False),('prerelease',False),('tag_name','different'),('target_commitish','main')]:refused(lambda key=key,value=value:m.verify_release(dict(release,**{key:value}),v))
asset={'id':1,'name':v['ASSET_NAME'],'state':'uploaded','size':123,'digest':'sha256:'+v['EXPECTED_SHA256']}
check(m.matching_asset([],v,123) is None);check(m.matching_asset([asset],v,123)==asset)
for key,value in [('id',True),('state','starter'),('size',122),('digest','sha256:'+'0'*64),('digest',None)]:refused(lambda key=key,value=value:m.matching_asset([dict(asset,**{key:value})],v,123))
refused(lambda:m.matching_asset([asset,asset],v,123))
with tempfile.TemporaryDirectory() as temp:
 root=pathlib.Path(temp);fixture=root/'fixture';fixture.mkdir();pkg=fixture/'package';pkg.mkdir();evidence=fixture/'evidence';evidence.mkdir()
 archive=pkg/'Rebase-Windows-x64-development-8c6ec4b8a41f.zip'
 with zipfile.ZipFile(archive,'w') as z:z.writestr('authored-control.txt','No executable content')
 v=dict(v,EXPECTED_SHA256=hashlib.sha256(archive.read_bytes()).hexdigest());size=archive.stat().st_size
 build={'status':'passed','commit':v['SOURCE_COMMIT'],'window_smoke_tested':True,'dependency_closure_checked':True,'app_local_modules_observed':True,'package':{'name':archive.name,'bytes':size,'sha256':v['EXPECTED_SHA256']}}
 def save(b): (evidence/'application-build.json').write_text(json.dumps(b))
 save(build);check(m.verify_package(evidence,pkg,v)==(archive,size))
 for key,value in [('status','failed'),('commit','0'*40),('window_smoke_tested',False),('dependency_closure_checked',False),('app_local_modules_observed',False)]:
  save(dict(build,**{key:value}));refused(lambda:m.verify_package(evidence,pkg,v))
 save(build)
 for key,value in [('name','other.zip'),('bytes',size-1),('sha256','0'*64)]:
  save(dict(build,package=dict(build['package'],**{key:value})));refused(lambda:m.verify_package(evidence,pkg,v))
 save(build);refused(lambda:m.verify_package(evidence,pkg,dict(v,EXPECTED_SHA256='0'*64)))
 extra=pkg/'other.zip';extra.write_bytes(archive.read_bytes());refused(lambda:m.verify_package(evidence,pkg,v));extra.unlink()
 original=archive.read_bytes();archive.write_bytes(bytes([original[0]^1])+original[1:]);refused(lambda:m.verify_package(evidence,pkg,v));archive.write_bytes(original)
 link=pkg/'linked';link.symlink_to(archive.name);refused(lambda:m.verify_package(evidence,pkg,v));link.unlink()
 real_api,real_gh=m.api,m.gh;os.environ['RUNNER_TEMP']=temp
 state={'assets':[],'calls':[]}
 good_asset=dict(asset,size=size,digest='sha256:'+v['EXPECTED_SHA256'])
 def fake_api(path,*,pages=False):
  if '/actions/runs/' in path:return run
  if '/git/matching-refs/' in path:return []
  if path.endswith('/releases?per_page=100'):return [release]
  if path.endswith('/assets?per_page=100'):return state['assets']
  return release
 def fake_gh(args,**kwargs):
  state['calls'].append(args)
  if args[:2]==['run','download']:
   name=args[args.index('--name')+1];dest=pathlib.Path(args[args.index('--dir')+1]);shutil.copytree(evidence if name=='windows-application-evidence' else pkg,dest)
  elif args[:2]==['release','upload']:
   check('--clobber' not in args);check(pathlib.Path(args[3]).read_bytes()==original);state['assets']=[good_asset]
   return None # Simulate client timeout after server accepted all bytes.
  else:raise AssertionError('Unexpected mutation')
  return b''
 m.api,m.gh=fake_api,fake_gh
 receipt=m.upload(v);check(receipt['outcome']=='uploaded' and receipt['release_remains_draft'] and not receipt['published']);check(sum(c[:2]==['release','upload'] for c in state['calls'])==1)
 state['calls']=[];receipt=m.upload(v);check(receipt['outcome']=='already-uploaded');check(not any(c[:2]==['release','upload'] for c in state['calls']))
 state['calls']=[];state['assets']=[dict(good_asset,state='starter')];refused(lambda:m.upload(v));check(not any(c[:2]==['release','upload'] for c in state['calls']))
 m.api,m.gh=real_api,real_gh
original_api=m.api
ref='refs/tags/'+v['RELEASE_TAG'];prefix='repos/'+v['GITHUB_REPOSITORY'];tagsha='a'*40
for refs in [[],[{'ref':ref+'-other','object':{'type':'commit','sha':'0'*40}}],[{'ref':ref,'object':{'type':'commit','sha':v['SOURCE_COMMIT']}}]]:
 m.api=lambda path, refs=refs:refs
 m.verify_tag(prefix,v);checks+=1
annotation={'sha':tagsha,'object':{'type':'commit','sha':v['SOURCE_COMMIT']}}
m.api=lambda path:([{'ref':ref,'object':{'type':'tag','sha':tagsha}}] if '/matching-refs/' in path else annotation)
m.verify_tag(prefix,v);checks+=1
for refs in [[{'ref':ref,'object':{'type':'commit','sha':'0'*40}}],[{'ref':ref,'object':{'type':'tree','sha':tagsha}}],{'message':'not found'},[{'ref':ref,'object':{'type':'commit','sha':'invalid'}}]]:
 m.api=lambda path, refs=refs:refs
 refused(lambda:m.verify_tag(prefix,v))
for obj in [{'type':'commit','sha':'0'*40},{'type':'tag','sha':tagsha}]:
 m.api=lambda path,obj=obj:([{'ref':ref,'object':{'type':'tag','sha':tagsha}}] if '/matching-refs/' in path else {'sha':tagsha,'object':obj})
 refused(lambda:m.verify_tag(prefix,v))
def failing_api(path):raise m.Refused('github-command-failed')
m.api=failing_api;refused(lambda:m.verify_tag(prefix,v))
m.api=original_api
print(json.dumps({'status':'passed','checks':checks,'network_calls':0,'remote_mutations':0,'control_scope':'Input validation, run/draft refusal, package custody, no-clobber, server-confirmed timeout/idempotence and resolved tag validation','source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'control_script_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),'python_version':sys.version.split()[0]}))
