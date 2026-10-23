import copy, hashlib, importlib.util, json, pathlib, tempfile, sys
root=pathlib.Path.cwd()
script=root/'Application/scripts/build-windows-app.py'
spec=importlib.util.spec_from_file_location('gate',script);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
evidence=pathlib.Path(sys.argv[1])
measured=json.loads(pathlib.Path(__file__).with_name('alpha-controls.json').read_text())['controls']
checks=0
with tempfile.TemporaryDirectory(prefix='rebase-alpha-gate-') as directory:
 path=pathlib.Path(directory)/'control.png';path.write_bytes((evidence/'native-app-visual.png').read_bytes())
 bounds={'outer_width':1100,'outer_height':788,'client_width':1084,'client_height':749,'dpi_x':96,'dpi_y':96}
 layout={key:measured[0][key] for key in ('alpha_minimum','alpha_254_pixels','alpha_255_pixels','alpha_below_254_pixels')}
 layout.update(total_pixels=1084*749,review_viewport_height=200,error_characters=100,footer_controls=[{'name':name,'x':10+i*200,'y':680,'width':170,'height':25} for i,name in enumerate(['Previous','Next','Cancel','Import Supported Data'])])
 def diagnostic(b,l):
  d={'schema':1,'screenshot':path.name,'png_sha256':mod.digest(path),'root_background_alpha':255,'window_bounds':b,'capture_layout':l}
  path.with_name(path.stem+'-alpha.json').write_text(json.dumps(d))
  return d
 def reject(b,l,minimum=False):
  global checks
  try:mod.require_cpr_review_layout(path,b,l,minimum_error=minimum)
  except RuntimeError:checks+=1
  else:raise AssertionError('invalid capture accepted')
 diagnostic(bounds,layout);mod.require_cpr_review_layout(path,bounds,layout);checks+=1
 for mutate in [lambda b,l:l.update(alpha_minimum=253),lambda b,l:l.update(alpha_below_254_pixels=1),lambda b,l:l.update(alpha_254_pixels=-1),lambda b,l:l.update(total_pixels=0),lambda b,l:l.update(review_viewport_height=0),lambda b,l:l['footer_controls'].pop(),lambda b,l:l['footer_controls'][0].update(name='Other'),lambda b,l:l['footer_controls'][0].update(x=-1),lambda b,l:l['footer_controls'][0].update(x=1084),lambda b,l:l['footer_controls'][0].update(y=749),lambda b,l:l['footer_controls'][0].update(width=float('nan')),lambda b,l:l['footer_controls'][0].update(height=0)]:
  b,l=copy.deepcopy(bounds),copy.deepcopy(layout);mutate(b,l);diagnostic(b,l);reject(b,l)
 diagnostic(bounds,layout);reject(bounds,layout,minimum=True)
 for key,value in [('png_sha256','0'*64),('root_background_alpha',254),('screenshot','wrong.png')]:
  d=diagnostic(bounds,layout);d[key]=value;path.with_name(path.stem+'-alpha.json').write_text(json.dumps(d));reject(bounds,layout)
 bad=measured[3];path.write_bytes((evidence/bad['path']).read_bytes())
 b=copy.deepcopy(bounds);b.update(client_width=bad['width'],client_height=bad['height'])
 l=copy.deepcopy(layout);l.update({key:bad[key] for key in ('alpha_minimum','alpha_254_pixels','alpha_255_pixels','alpha_below_254_pixels')});l['total_pixels']=bad['width']*bad['height'];diagnostic(b,l);reject(b,l)
print(json.dumps({'schema':1,'suite':'cpr-review-capture-package-gates','checks':checks,'failures':0,'boundaries':'Synthetic layout receipts over retained PNG bytes; native WPF verification remains pending.'}))
