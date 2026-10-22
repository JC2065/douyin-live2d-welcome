// Isolated browser fixtures: never submits fake likes/gifts/comments to a live room.
const {chromium}=require('playwright');
(async()=>{
  const browser=await chromium.launch({headless:true,channel:'msedge',args:['--autoplay-policy=no-user-gesture-required']});
  try {
    const page=await browser.newPage();
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    await page.addInitScript(()=>{
      const resume=AudioContext.prototype.resume;
      AudioContext.prototype.resume=function(){return window.forceAudioBlocked?Promise.resolve():resume.call(this)};
    });
    let hold=true,index=0,blocked=0;
    const finished=[];
    await page.route('**/api/player/claim',route=>route.fulfill({json:{ok:true}}));
    await page.route('**/api/player/release',route=>route.fulfill({json:{ok:true}}));
    const dataBytes=16000;
    const wav=Buffer.alloc(44+dataBytes);
    wav.write('RIFF',0);wav.writeUInt32LE(36+dataBytes,4);wav.write('WAVEfmt ',8);
    wav.writeUInt32LE(16,16);wav.writeUInt16LE(1,20);wav.writeUInt16LE(1,22);
    wav.writeUInt32LE(8000,24);wav.writeUInt32LE(16000,28);wav.writeUInt16LE(2,32);wav.writeUInt16LE(16,34);
    wav.write('data',36);wav.writeUInt32LE(dataBytes,40);
    for(let i=0;i<8000;i++)wav.writeInt16LE(Math.round(1000*Math.sin(2*Math.PI*440*i/8000)),44+2*i);
    await page.route('**/audio/fixture.wav',route=>route.fulfill({contentType:'audio/wav',body:wav}));
    const events=[3,3,1].map((people,i)=>({id:'fixture-'+i,seq:i+1,generation:0,attempt:1,source:'simulation',
      kind:i===0?'chat':i===1?'gift':'welcome',text:'连续播放测试 '+(i+1),people,
      created:Date.now()/1000,audio:'/audio/fixture.wav'}));
    await page.route('**/api/events?**',async route=>{
      const ready=new URL(route.request().url()).searchParams.get('ready')!=='false';
      await route.fulfill({json:{server_id:'fixture',busy:false,muted:false,events:!hold&&ready&&index<events.length?[events[index]]:[]}});
    });
    await page.route('**/api/playback',async route=>{
      const body=route.request().postDataJSON();
      if(body.phase==='blocked')blocked++;
      if(body.phase==='finished'){finished.push(body.event);index++}
      await route.fulfill({json:{ok:true}});
    });
    await page.goto('http://127.0.0.1:18765/overlay');
    await page.waitForFunction(()=>window.modelReady,{timeout:30000});
    await page.locator('#enable').click();
    await page.evaluate(async()=>{await audioContext.suspend();window.forceAudioBlocked=true});
    hold=false;
    await page.locator('#enable').filter({hasText:'恢复'}).waitFor({timeout:10000});
    await page.waitForTimeout(1500);
    if(!await page.locator('#enable').isVisible())throw Error('Recovery button disappeared');
    if(!blocked||finished.length)throw Error('Blocked audio was reported as finished');
    await page.evaluate(()=>window.forceAudioBlocked=false);
    await page.locator('#enable').click();
    await page.waitForFunction(()=>window.lastWelcome==='连续播放测试 3',{timeout:35000});
    if(finished.length!==3||new Set(finished).size!==3)throw Error('Lost/duplicated playback reports');
    if(errors.length)throw Error(errors.join('\n'));
    console.log(JSON.stringify({recovery:true,completedGroups:finished.length,people:7,pageErrors:errors}));
  }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
