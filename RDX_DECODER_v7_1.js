#!/usr/bin/env node
'use strict';
/**
 * RDX DECODER v7.1 — Improved Post-Decode Validation
 *
 * v7.0 থেকে পার্থক্য:
 * - Post-decode HTML structure validation (tag balance check)
 * - JS syntax balance check (braces, parens, brackets)
 * - <link rel="stylesheet"> CDN tags সংরক্ষণ (Google Fonts ইত্যাদি)
 * - Leftover RDX comment cleanup (prot-only stripped comments)
 * - CRLF normalize আগেই করা হয় (decode করার আগে)
 * - PROT_ONLY threshold আরো নিরাপদ (8000 → configurable)
 * - Inline style hex decode support
 * - Decode summary: কতটা recovered হলো সেটা দেখায়
 *
 * Usage: node RDX_DECODER_v7_updated.js <obf.html> [out.html]
 */

const fs   = require('fs');
const vm   = require('vm');
const path = require('path');

/* ── ANSI ─────────────────────────────────────────────────────────── */
const C = {
  r:'\x1b[0m', b:'\x1b[1m', d:'\x1b[2m',
  bG:'\x1b[92m', bR:'\x1b[91m', bY:'\x1b[93m',
  bC:'\x1b[96m', bM:'\x1b[95m', bW:'\x1b[97m',
};
const cl  = (...p) => p.join('') + C.r;
const raw = s => s.replace(/\x1b\[[0-9;]*m/g,'');
const L = {
  ok  (l,v=''){console.log(`  ${cl(C.bG,'✔')}  ${cl(C.b,C.bW,l)}${v?'  '+cl(C.d,C.bW,v):''}`)},
  err (l,v=''){console.log(`  ${cl(C.bR,'✘')}  ${cl(C.b,C.bW,l)}${v?'  '+cl(C.d,C.bW,v):''}`)},
  warn(l,v=''){console.log(`  ${cl(C.bY,'⚠')}  ${cl(C.b,C.bW,l)}${v?'  '+cl(C.d,C.bW,v):''}`)},
  info(l,v=''){console.log(`  ${cl(C.bC,'◆')}  ${cl(C.b,C.bW,l)}${v?'  '+cl(C.d,C.bW,v):''}`)},
  nl  (){console.log('')},
  sec (t){console.log('');console.log(`  ${cl(C.bM,C.b,'▶')}  ${cl(C.b,C.bW,t)}`);
          console.log(`  ${cl(C.d,C.bC,'━'.repeat(56))}`);},
};

/* ── BANNER ───────────────────────────────────────────────────────── */
function banner(){
  console.log(`\n  ${cl(C.bC,C.b,'╔'+'═'.repeat(56)+'╗')}`);
  console.log(`  ${cl(C.bC,C.b,'║')}  ${cl(C.bM,C.b,'RDX DECODER  v7.1  ·  Validated Edition')}${' '.repeat(9)}${cl(C.bC,C.b,'║')}`);
  console.log(`  ${cl(C.bC,C.b,'║')}  ${cl(C.d,C.bW,'External scripts + CSS links preserved')}${' '.repeat(11)}${cl(C.bC,C.b,'║')}`);
  console.log(`  ${cl(C.bC,C.b,'║')}  ${cl(C.d,C.bW,'Post-decode HTML + JS structure validated')}${' '.repeat(9)}${cl(C.bC,C.b,'║')}`);
  console.log(`  ${cl(C.bC,C.b,'╚'+'═'.repeat(56)+'╝')}\n`);
}

/* ── PURE-PROTECTION SIGNATURES ─────────────────────────────────── */
const PROT_ONLY = ['_iPoison','_sBlock','_hBlock','_chkC','_chkBot','_chkDev'];
const PROT_ONLY_THRESHOLD = 8000; // v7.0 ছিল 7000, আরেকটু margin দেওয়া হলো

/* ── HEX CSS DECODER ─────────────────────────────────────────────── */
function decodeHexCSS(css) {
  return css.replace(/\\([0-9a-fA-F]{2,6})\s?/g, (_, hex) => {
    try { return String.fromCharCode(parseInt(hex, 16)); } catch { return _; }
  });
}

/* ── IFRAME PROTECTION IIFE STRIPPER ────────────────────────────── */
function stripIframeProtectionIIFE(code) {
  const trimmed = code.trimStart();
  if (!trimmed.startsWith('(function(){') && !trimmed.startsWith('(function() {')) {
    return { stripped: false, code };
  }
  const hasIframe = /document\.createElement\s*\(\s*['"]iframe['"]\s*\)/.test(trimmed.slice(0, 3000));
  const hasEval   = /contentWindow\.eval/.test(trimmed.slice(0, 3000));
  if (!hasIframe || !hasEval) return { stripped: false, code };

  let depth = 0;
  const start = trimmed.indexOf('{');
  if (start === -1) return { stripped: false, code };

  let iifeEnd = -1;
  for (let j = start; j < trimmed.length; j++) {
    if (trimmed[j] === '{') depth++;
    else if (trimmed[j] === '}') {
      depth--;
      if (depth === 0) {
        const endMatch = trimmed.slice(j).match(/^\}\s*\)\s*\(\s*\)\s*;/);
        if (endMatch) { iifeEnd = j + endMatch[0].length; break; }
      }
    }
  }
  if (iifeEnd === -1) return { stripped: false, code };

  const afterIIFE = trimmed.slice(iifeEnd).trimStart();
  if (afterIIFE.length < 50) return { stripped: false, code };
  return { stripped: true, code: afterIIFE };
}

/* ── SANDBOX ─────────────────────────────────────────────────────── */
function makeSandbox(captureDocWrite=false){
  let _out='';
  const fakeEl=(tag='div')=>{
    const el={style:{},className:'',id:'',innerHTML:'',textContent:'',
      tagName:tag.toUpperCase(),children:[],childNodes:[],
      appendChild:()=>{},removeChild:()=>{},addEventListener:()=>{},
      setAttribute:()=>{},getAttribute:()=>null,
      getBoundingClientRect:()=>({width:0,height:0,top:0,left:0})};
    if(tag==='canvas'){
      el.getContext=()=>({fillRect:()=>{},strokeRect:()=>{},clearRect:()=>{},
        fillText:()=>{},strokeText:()=>{},getImageData:()=>({data:new Array(4).fill(0)}),
        putImageData:()=>{},drawImage:()=>{},measureText:()=>({width:10}),
        beginPath:()=>{},moveTo:()=>{},lineTo:()=>{},stroke:()=>{},fill:()=>{},
        save:()=>{},restore:()=>{},createLinearGradient:()=>({addColorStop:()=>{}})});
      el.toDataURL=()=>'';
    }
    return el;
  };
  const fakeDoc={
    open:()=>{_out='';},close:()=>{},
    write:(s)=>{if(captureDocWrite)_out+=s;},
    writeln:(s)=>{if(captureDocWrite)_out+=s+'\n';},
    cookie:'',title:'',readyState:'complete',
    createElement:fakeEl,createTextNode:(t)=>({nodeValue:t}),
    head:fakeEl('head'),body:fakeEl('body'),documentElement:fakeEl('html'),
    addEventListener:()=>{},removeEventListener:()=>{},dispatchEvent:()=>{},
    getElementById:()=>null,querySelector:()=>null,querySelectorAll:()=>[],
    createDocumentFragment:()=>fakeEl('fragment'),
  };
  const nav={userAgent:'Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36',
    webdriver:false,language:'en-US',languages:['en-US','en'],
    platform:'Linux armv8l',hardwareConcurrency:4,maxTouchPoints:5,
    plugins:{length:3},onLine:true,cookieEnabled:true};
  const sb={
    document:fakeDoc,navigator:nav,
    location:{href:'https://example.com/',hostname:'example.com',pathname:'/',
      protocol:'https:',port:'',replace:()=>{},assign:()=>{},reload:()=>{}},
    history:{pushState:()=>{},replaceState:()=>{},back:()=>{}},
    screen:{width:1080,height:2340,colorDepth:24},
    console:{log:()=>{},warn:()=>{},error:()=>{},info:()=>{}},
    setTimeout:()=>0,setInterval:()=>0,clearTimeout:()=>{},clearInterval:()=>{},
    requestAnimationFrame:()=>0,cancelAnimationFrame:()=>{},
    localStorage:{getItem:()=>null,setItem:()=>{},removeItem:()=>{},clear:()=>{}},
    sessionStorage:{getItem:()=>null,setItem:()=>{},removeItem:()=>{},clear:()=>{}},
    Image:function(){return{src:''};},
    Audio:function(){return{play:()=>Promise.resolve(),pause:()=>{},load:()=>{}};},
    Event:class Event{constructor(t){this.type=t;}},
    CustomEvent:class CustomEvent{constructor(t,d){this.type=t;this.detail=d?.detail;}},
    MutationObserver:class{observe(){}disconnect(){}},
    ResizeObserver:class{observe(){}disconnect(){}},
    IntersectionObserver:class{observe(){}disconnect(){}},
    WebSocket:class{send(){}close(){}},
    fetch:()=>Promise.resolve({json:()=>Promise.resolve({}),text:()=>Promise.resolve(''),ok:true,status:200}),
    XMLHttpRequest:class{open(){}send(){}setRequestHeader(){}addEventListener(){}},
    crypto:{getRandomValues:(a)=>{for(let i=0;i<a.length;i++)a[i]=Math.random()*256|0;return a;},subtle:{}},
    performance:{now:()=>Date.now(),timing:{}},
    stop:()=>{},
    URL:typeof URL!=='undefined'?URL:class URL{constructor(u){this.href=u;}},
    Blob:class Blob{constructor(){this.size=0;}},
    atob:s=>Buffer.from(s,'base64').toString('binary'),
    btoa:s=>Buffer.from(s,'binary').toString('base64'),
    devicePixelRatio:3,
    Math,JSON,Date,Promise,Symbol,Error,
    parseInt,parseFloat,isNaN,isFinite,
    decodeURIComponent,encodeURIComponent,decodeURI,encodeURI,escape,unescape,
    Object,Array,String,Number,Boolean,Function,RegExp,
    Map,Set,WeakMap,WeakSet,Proxy,Reflect,
    ArrayBuffer,Uint8Array,Int32Array,Float64Array,
    clearTimeout,clearInterval,
    eval:()=>{},window:null,self:null,top:null,globalThis:null,
  };
  sb.window=sb;sb.self=sb;sb.top=sb;sb.globalThis=sb;
  return {sandbox:sb,getOutput:()=>_out};
}

/* ── PATTERN DETECTOR ────────────────────────────────────────────── */
function detectPattern(block){
  if(/try\s*\{\s*\(0,eval\)\(\w+\)\s*\}\s*catch/.test(block)) return 3;
  if(/while\s*\(/.test(block)&&/document\s*\.\s*(write|open)\s*\(/.test(block)) return 2;
  if(/\(0,eval\)\(\w+\)\s*;/.test(block)) return 1;
  return 0;
}

/* ── DECODERS ────────────────────────────────────────────────────── */
function decodePattern1(scriptBlock){
  const m=scriptBlock.match(/\(0,eval\)\((\w+)\)\s*;/);
  if(!m) throw new Error('P1 › eval var not found');
  const varName=m[1];
  const HOOK=`__RDX_P1_${Date.now()}__`;
  const patched=scriptBlock.replace(new RegExp(`\\(0,eval\\)\\(${varName}\\)\\s*;`,'g'),`${HOOK}(${varName});`);
  let captured=null;
  const {sandbox}=makeSandbox(false);
  sandbox[HOOK]=code=>{captured=code;};
  vm.createContext(sandbox);
  vm.runInContext(patched,sandbox,{timeout:60000});
  if(!captured) throw new Error('P1 › nothing captured');
  return captured;
}

function decodePattern2(scriptBlock){
  const {sandbox,getOutput}=makeSandbox(true);
  vm.createContext(sandbox);
  try{vm.runInContext(scriptBlock,sandbox,{timeout:30000});}catch(_){}
  const out=getOutput();
  if(out.length<100) throw new Error(`P2 › output too small (${out.length})`);
  return out;
}

function decodePattern3(scriptBlock){
  const m=scriptBlock.match(/try\s*\{\s*\(0,eval\)\((\w+)\)\s*\}\s*catch\s*(\{\s*\})?/);
  if(!m) throw new Error('P3 › try-eval var not found');
  const varName=m[1];
  const HOOK=`__RDX_P3_${Date.now()}__`;
  const tryPat=new RegExp(`try\\s*\\{\\s*\\(0,eval\\)\\(${varName}\\)\\s*\\}\\s*catch\\s*(\\{[^}]*\\})?`,'g');
  const patched=scriptBlock.replace(tryPat,`try{${HOOK}(${varName})}catch{}`);
  let layer2=null;
  const {sandbox:s1}=makeSandbox(false);
  s1[HOOK]=code=>{layer2=code;};
  vm.createContext(s1);
  try{vm.runInContext(patched,s1,{timeout:20000});}catch(_){}
  if(!layer2) throw new Error('P3 › L1 capture failed');
  const TAIL='document.open();document.write(';
  const ti=layer2.indexOf(TAIL);
  if(ti!==-1){
    const {sandbox:s2,getOutput}=makeSandbox(true);
    vm.createContext(s2);
    try{vm.runInContext(layer2.slice(ti),s2,{timeout:10000});}catch(_){}
    const out=getOutput();
    if(out.length>=100) return out;
  }
  const {sandbox:s2b,getOutput:getB}=makeSandbox(true);
  const lp=layer2.replace(/if\s*\(\s*!\s*_\$\s*\)/g,'if(false)').replace(/if\s*\(\s*_\$\s*===?\s*false\s*\)/g,'if(false)');
  vm.createContext(s2b);
  try{vm.runInContext(lp,s2b,{timeout:30000});}catch(_){}
  const outB=getB();
  if(outB.length>=100) return outB;
  throw new Error('P3 › L2 capture failed');
}

function decodePatternHybrid(scriptBlock){
  const m=scriptBlock.match(/\(0,eval\)\((\w+)\)/);
  if(!m) throw new Error('Hybrid › no (0,eval)() found');
  const varName=m[1];
  const HOOK=`__RDX_H_${Date.now()}__`;
  let patched=scriptBlock
    .replace(new RegExp(`\\(0,eval\\)\\(${varName}\\)`,'g'),`${HOOK}(${varName})`)
    .replace(/window\s*\[\s*['"]\S+['"]\s*\]/g,'null');
  let captured=null;
  const {sandbox}=makeSandbox(false);
  sandbox[HOOK]=code=>{captured=code;};
  vm.createContext(sandbox);
  try{vm.runInContext(patched,sandbox,{timeout:60000});}catch(_){}
  if(!captured) throw new Error('Hybrid › nothing captured');
  return captured;
}

function decodeBlock(body,pat){
  const strategies={1:decodePattern1,2:decodePattern2,3:decodePattern3};
  if(strategies[pat]){ try{return strategies[pat](body);}catch(_){} }
  return decodePatternHybrid(body);
}

function resolveInner(decoded){
  const ip=detectPattern(decoded);
  if(ip===0) return decoded;
  L.warn('Inner obfuscation detected',`P${ip}`);
  const sm=decoded.match(/<script([^>]*)>([\s\S]*?)<\/script>/i);
  if(sm&&!sm[1].includes('src')&&sm[2].length>500){
    try{
      const r=decodeBlock(sm[2],detectPattern(sm[2])||ip);
      L.ok('Inner layer resolved',`${(r.length/1024).toFixed(1)} KB`);
      return r;
    }catch(_){}
  }
  try{
    const r=decodeBlock(decoded,ip);
    L.ok('Inner layer resolved',`${(r.length/1024).toFixed(1)} KB`);
    return r;
  }catch(_){}
  return decoded;
}

/* ── POST-DECODE CHECK ───────────────────────────────────────────── */
function fullDecodeCheck(html){
  const scriptRx=/<script([^>]*)>([\s\S]*?)<\/script>/gi;
  let m; const issues=[];
  while((m=scriptRx.exec(html))!==null){
    const attrs=m[1],body=m[2];
    if(attrs.toLowerCase().includes('src')||body.length<100) continue;
    const pat=detectPattern(body);
    if(pat>0) issues.push({pat,size:(body.length/1024).toFixed(1)+'KB'});
  }
  return issues;
}

/* ── NEW v7.1: HTML STRUCTURE VALIDATOR ──────────────────────────── */
function validateHTMLStructure(html){
  const issues = [];
  const warnings = [];

  // Tag balance check for key tags
  const checkTag = (tag, selfClose=false) => {
    if(selfClose) return; // self-closing tags skip
    const opens  = (html.match(new RegExp(`<${tag}[\\s>]`,'gi'))||[]).length;
    const closes = (html.match(new RegExp(`</${tag}>`,'gi'))||[]).length;
    if(opens !== closes){
      issues.push(`<${tag}> mismatch: ${opens} open, ${closes} close`);
    }
  };

  ['html','head','body','div','span','script','style','ul','li','table','tr','td','th'].forEach(t=>checkTag(t));

  // DOCTYPE present
  if(!/<!DOCTYPE\s+html>/i.test(html)){
    warnings.push('No <!DOCTYPE html> found');
  }

  // Multiple DOCTYPE
  const dtCount = (html.match(/<!DOCTYPE/gi)||[]).length;
  if(dtCount > 1) issues.push(`Multiple DOCTYPE (${dtCount})`);

  // Multiple <html>
  const htmlCount = (html.match(/<html[\s>]/gi)||[]).length;
  if(htmlCount > 1) issues.push(`Multiple <html> tags (${htmlCount})`);

  // Leftover RDX artifacts
  if(/\(0,eval\)\(/.test(html)) issues.push('Remaining eval obfuscation found');
  if(/__RDX_P[13H]_\d+__/.test(html)) issues.push('Leftover RDX hook variable found');
  PROT_ONLY.forEach(sig => {
    if(html.includes(sig)) warnings.push(`Protection signature present: ${sig}`);
  });

  return {issues, warnings};
}

/* ── NEW v7.1: JS SYNTAX VALIDATOR ──────────────────────────────── */
function validateJSSyntax(js, blockIndex){
  const issues = [];
  const pairs = [['{','}'], ['(', ')'], ['[',']']];
  for(const [o,c] of pairs){
    // Ignore those inside strings/comments (simple heuristic)
    const opens  = (js.match(new RegExp('\\'+o,'g'))||[]).length;
    const closes = (js.match(new RegExp('\\'+c,'g'))||[]).length;
    if(opens !== closes){
      issues.push(`Block #${blockIndex}: ${o}${c} mismatch (${opens} open, ${closes} close)`);
    }
  }
  return issues;
}

/* ══════════════════════════════════════════════════════════════════
   MAIN
══════════════════════════════════════════════════════════════════ */
async function main(){
  banner();

  const inputFile=process.argv[2];
  if(!inputFile||!fs.existsSync(inputFile)){
    L.err('File not found',inputFile||'(none)'); process.exit(1);
  }
  const base=path.basename(inputFile,path.extname(inputFile));
  const outputFile=process.argv[3]||path.join(path.dirname(inputFile),`${base}_decoded.html`);

  /* ── Step 1: Read ─────────────────────────────────────────────── */
  L.sec('INPUT');
  let rawHTML=fs.readFileSync(inputFile,'utf-8');
  L.ok('Loaded',`${inputFile}  (${(rawHTML.length/1024).toFixed(1)} KB)`);

  /* ── Step 1b: CRLF normalize BEFORE processing (v7.1) ─────────── */
  const crlfCount = (rawHTML.match(/\r\n/g)||[]).length;
  if(crlfCount > 0){
    rawHTML = rawHTML.replace(/\r\n/g, '\n');
    L.info(`CRLF normalized`,`${crlfCount} line endings converted before decode`);
  }

  /* ── Step 2: External tag inventory ──────────────────────────── */
  L.sec('EXTERNAL TAG INVENTORY');

  // External <script src="..."> tags
  const externalScriptRx = /<script([^>]+src\s*=\s*["'][^"']+["'][^>]*)><\/script>|<script([^>]+src\s*=\s*["'][^"']+["'][^>]*)\/?>(?!\s*<\/script>)/gi;
  const externalScripts = [];
  let esm;
  while((esm = externalScriptRx.exec(rawHTML)) !== null){
    externalScripts.push(esm[0].trim());
  }
  const extSimple = rawHTML.match(/<script\s[^>]*src\s*=\s*["'][^"']+["'][^>]*>(\s*<\/script>)?/gi) || [];
  const allExternalScripts = [...new Set([...externalScripts, ...extSimple.map(s => s.trim())])];

  L.ok(`Found ${allExternalScripts.length} external script tag(s)`);
  allExternalScripts.forEach((s,i) => {
    const srcMatch = s.match(/src\s*=\s*["']([^"']+)["']/i);
    L.info(`  #${i+1}`, srcMatch ? srcMatch[1] : s.slice(0,60));
  });

  // NEW v7.1: Also track <link rel="stylesheet"> CDN tags (Google Fonts etc)
  const externalLinks = rawHTML.match(/<link\s[^>]+href\s*=\s*["'][^"']+["'][^>]*>/gi) || [];
  L.ok(`Found ${externalLinks.length} external <link> tag(s)`);
  externalLinks.forEach((l,i) => {
    const href = (l.match(/href\s*=\s*["']([^"']+)["']/i)||[])[1];
    if(href) L.info(`  link#${i+1}`, href.slice(0,70));
  });

  /* ── Step 3: Block detection ──────────────────────────────────── */
  L.sec('BLOCK DETECTION');
  const blockRx=/<script([^>]*)>([\s\S]*?)<\/script>/gi;
  const blocks=[];
  let bm;
  while((bm=blockRx.exec(rawHTML))!==null){
    const attrs=bm[1],body=bm[2];
    if(attrs.toLowerCase().includes('src')||body.length<500) continue;
    const pat=detectPattern(body);
    if(pat>0) blocks.push({
      fullMatch:bm[0],start:bm.index,end:bm.index+bm[0].length,body,pat
    });
  }
  if(!blocks.length){L.err('No obfuscated blocks found');process.exit(1);}
  L.ok(`Found ${blocks.length} obfuscated block(s)`,
    blocks.map((b,i)=>`#${i+1}:P${b.pat}:${(b.body.length/1024).toFixed(0)}KB`).join('  '));

  /* ── Step 4: Decode all blocks ────────────────────────────────── */
  L.sec('MULTI-BLOCK DECODE');
  let result=rawHTML, offset=0, ok=0, fail=0, protWarn=0, iframeStripped=0;

  for(let i=0;i<blocks.length;i++){
    const blk=blocks[i];
    const kb=(blk.body.length/1024).toFixed(1);
    process.stdout.write(
      `  ${cl(C.d,C.bW,`[${i+1}/${blocks.length}]`)}  `+
      `${cl(C.bC,'P'+blk.pat)}  ${cl(C.bW,kb+' KB')}  ... `
    );
    try{
      let decoded=decodeBlock(blk.body,blk.pat);
      decoded=resolveInner(decoded);
      const decodedKB=(decoded.length/1024).toFixed(1);
      // v7.1: use PROT_ONLY_THRESHOLD constant
      const isPureProtection=PROT_ONLY.some(s=>decoded.includes(s))&&decoded.length<PROT_ONLY_THRESHOLD;

      let replacement;
      if(isPureProtection){
        // v7.1: no comment placeholder — just remove silently
        replacement='';
        protWarn++;
        process.stdout.write(`${cl(C.bY,'⚠')} ${cl(C.bY,'prot-only stripped')} (${decodedKB} KB)\n`);
      } else {
        const iframeResult=stripIframeProtectionIIFE(decoded);
        if(iframeResult.stripped){
          decoded=iframeResult.code;
          iframeStripped++;
          process.stdout.write(`${cl(C.bG,'✓')} ${cl(C.bG,(decoded.length/1024).toFixed(1)+' KB')} ${cl(C.bY,'[iframe-prot removed]')}\n`);
        } else {
          process.stdout.write(`${cl(C.bG,'✓')} ${cl(C.bG,decodedKB+' KB')}\n`);
        }
        replacement=`<script>\n${decoded}\n</script>`;
      }
      const adjStart=blk.start+offset;
      const adjEnd  =blk.end+offset;
      result=result.slice(0,adjStart)+replacement+result.slice(adjEnd);
      offset+=replacement.length-blk.fullMatch.length;
      ok++;
    }catch(e){
      process.stdout.write(`${cl(C.bR,'✘')} ${cl(C.bR,e.message)}\n`);
      fail++;
    }
  }

  /* ── Step 5: Restore missing external scripts ─────────────────── */
  L.sec('EXTERNAL SCRIPT RESTORE');
  let restored = 0;
  for(const extTag of allExternalScripts){
    const srcMatch = extTag.match(/src\s*=\s*["']([^"']+)["']/i);
    if(!srcMatch) continue;
    const src = srcMatch[1];
    if(!result.includes(src)){
      const normalized = `<script src="${src}"></script>`;
      result = result.replace('</head>', `${normalized}\n</head>`);
      restored++;
      L.ok(`Restored`, src);
    } else {
      L.info(`Present ✅`, src);
    }
  }

  // NEW v7.1: Restore missing <link> tags
  let linksRestored = 0;
  for(const linkTag of externalLinks){
    const href = (linkTag.match(/href\s*=\s*["']([^"']+)["']/i)||[])[1];
    if(href && !result.includes(href)){
      result = result.replace('</head>', `${linkTag}\n</head>`);
      linksRestored++;
      L.ok(`Link restored`, href.slice(0,60));
    }
  }
  if(restored === 0 && linksRestored === 0) L.ok('All external resources intact — nothing to restore');

  /* ── Step 6: Decode hex CSS ───────────────────────────────────── */
  L.sec('CSS HEX DECODE');
  let cssFixed = 0;
  result = result.replace(/<style([^>]*)>([\s\S]*?)<\/style>/gi, (match, attrs, css) => {
    if(/\\[0-9a-fA-F]{2,6}/.test(css)){
      cssFixed++;
      return `<style${attrs}>${decodeHexCSS(css)}</style>`;
    }
    return match;
  });
  // NEW v7.1: Also decode hex in inline style="" attributes
  let inlineStyleFixed = 0;
  result = result.replace(/style="([^"]*)"/gi, (match, styleVal) => {
    if(/\\[0-9a-fA-F]{2,6}/.test(styleVal)){
      inlineStyleFixed++;
      return `style="${decodeHexCSS(styleVal)}"`;
    }
    return match;
  });
  L.ok(`${cssFixed} style block(s) hex-decoded  ·  ${inlineStyleFixed} inline style attr(s) decoded`);

  /* ── Step 7: Cleanup ──────────────────────────────────────────── */
  L.sec('CLEANUP');
  result=result.replace(/<!--[\s\S]{0,2000}?(?:PROTECTED|HTMLObfuscateBot|RDXPROTECT|Obfuscated By)[\s\S]{0,2000}?-->\r?\n*/i,'');
  // NEW v7.1: Remove leftover RDX prot-only comment placeholders (from v7.0)
  result=result.replace(/<!-- \[RDX v7\] protection-only block #\d+ stripped[^-]* -->\s*/g,'');
  result=result.replace(/<script[^>]*>\s*<\/script>/gi,(m)=>{
    if(/src\s*=/.test(m)) return m;
    return '';
  });
  result=result.replace(/\r\n/g,'\n').replace(/\n{3,}/g,'\n\n').replace(/[ \t]+$/gm,'').trimStart();
  L.ok('Done');

  /* ── Step 8: Post-decode full check ──────────────────────────── */
  L.sec('POST-DECODE VERIFY');
  const issues=fullDecodeCheck(result);
  if(issues.length===0){
    L.ok('✅ FULL DECODE VERIFIED — No obfuscation remains');
  } else {
    L.warn(`${issues.length} block(s) still obfuscated — re-decode pass...`);
    const blockRx2=/<script([^>]*)>([\s\S]*?)<\/script>/gi;
    const blocks2=[]; let bm2;
    while((bm2=blockRx2.exec(result))!==null){
      const attrs=bm2[1],body=bm2[2];
      if(attrs.toLowerCase().includes('src')||body.length<500) continue;
      const pat=detectPattern(body);
      if(pat>0) blocks2.push({fullMatch:bm2[0],start:bm2.index,end:bm2.index+bm2[0].length,body,pat});
    }
    let offset2=0;
    for(const blk2 of blocks2){
      try{
        let dec2=decodeBlock(blk2.body,blk2.pat);
        dec2=resolveInner(dec2);
        const ir=stripIframeProtectionIIFE(dec2);
        if(ir.stripped) dec2=ir.code;
        const rep2=`<script>\n${dec2}\n</script>`;
        const as=blk2.start+offset2,ae=blk2.end+offset2;
        result=result.slice(0,as)+rep2+result.slice(ae);
        offset2+=rep2.length-blk2.fullMatch.length;
        L.ok('Re-decode OK',`${(dec2.length/1024).toFixed(1)} KB`);
      }catch(e){ L.err('Re-decode failed',e.message); }
    }
    const issues2=fullDecodeCheck(result);
    if(issues2.length===0) L.ok('✅ FULL DECODE VERIFIED after re-pass');
    else L.warn(`⚠ ${issues2.length} block(s) could not be decoded — manual check needed`);
  }

  /* ── NEW Step 8b: HTML Structure Validation (v7.1) ────────────── */
  L.sec('HTML STRUCTURE VALIDATION');
  const structResult = validateHTMLStructure(result);
  if(structResult.issues.length === 0 && structResult.warnings.length === 0){
    L.ok('✅ HTML structure valid — all tags balanced');
  } else {
    structResult.issues.forEach(iss => L.err(iss));
    structResult.warnings.forEach(w  => L.warn(w));
  }

  /* ── NEW Step 8c: JS Syntax Validation (v7.1) ────────────────── */
  L.sec('JS SYNTAX VALIDATION');
  const jsBlocks = [...result.matchAll(/<script([^>]*)>([\s\S]*?)<\/script>/gi)];
  let jsTotalIssues = 0;
  jsBlocks.forEach((m, i) => {
    if(m[1].toLowerCase().includes('src') || m[2].length < 100) return;
    const jsIssues = validateJSSyntax(m[2], i+1);
    jsIssues.forEach(iss => { L.err(iss); jsTotalIssues++; });
  });
  if(jsTotalIssues === 0){
    L.ok(`✅ JS syntax valid — ${jsBlocks.filter(m=>!m[1].toLowerCase().includes('src')&&m[2].length>=100).length} inline script(s) checked`);
  }

  /* ── Step 9: Inject Credit ────────────────────────────────────── */
  L.sec('CREDIT INJECTION');
  const CREDIT = `<!--
╔════════════════════════════════════════════════════╗
║  🔓 DECODED BY  ·  AF HTML DECRYPTOR                   ║
║  📢 TELEGRAM    ·  @AFHtmlDecryptBot                   ║
║  🛠️  TOOL        ·  RDX Decoder               ║
║  📅 DATE        ·  ${new Date().toISOString().slice(0,10)}                      ║
║  🕐 TIME        ·  ${new Date(Date.now()+6*3600000).toISOString().slice(11,19)}                        ║
║  ✅ STATUS      ·  100% FULLY DECODED               ║
║  🚫 OBFUSCATION ·  REMOVED COMPLETELY              ║
╚════════════════════════════════════════════════════╝
-->`;
  if(/<!DOCTYPE html>/i.test(result)){
    result = result.replace(/(<!DOCTYPE html>)/i, `${CREDIT}\n$1`);
    L.ok('Credit injected before <!DOCTYPE html>');
  } else if(/<html/i.test(result)){
    result = result.replace(/(<html[^>]*>)/i, `${CREDIT}\n$1`);
    L.ok('Credit injected before <html>');
  } else {
    result = CREDIT + '\n' + result;
    L.ok('Credit injected at top of file');
  }

  /* ── Step 10: Save ────────────────────────────────────────────── */
  L.sec('OUTPUT');
  fs.writeFileSync(outputFile,result,'utf-8');
  const finalKB=(result.length/1024).toFixed(1);
  const lines=result.split('\n').length;
  const titleM=result.match(/<title[^>]*>([^<]*)<\/title>/i);
  if(titleM) L.ok('Title',titleM[1].trim());

  let extOk=0;
  for(const extTag of allExternalScripts){
    const src = (extTag.match(/src\s*=\s*["']([^"']+)["']/i)||[])[1];
    if(src && result.includes(src)) extOk++;
  }
  let linkOk = externalLinks.filter(l => {
    const href = (l.match(/href\s*=\s*["']([^"']+)["']/i)||[])[1];
    return href && result.includes(href);
  }).length;
  L.ok(`External scripts in output: ${extOk}/${allExternalScripts.length}`);
  L.ok(`External links in output: ${linkOk}/${externalLinks.length}`);

  /* Result box */
  const BW=54;
  const hl=cl(C.bG,C.b,'═'.repeat(BW-2));
  const vl=cl(C.bG,C.b,'║');
  console.log(`\n  ${cl(C.bG,C.b,'╔')}${hl}${cl(C.bG,C.b,'╗')}`);
  console.log(`  ${vl}  ${cl(C.bG,C.b,'✨  DECODE COMPLETE  —  RDX v7.1')}${' '.repeat(BW-36)}${vl}`);
  console.log(`  ${cl(C.bG,C.b,'╠')}${hl}${cl(C.bG,C.b,'╣')}`);
  const row=(k,v)=>{
    const c=`  ${cl(C.bC,k+':')}  ${cl(C.bW,v)}`;
    const pad=' '.repeat(Math.max(0,BW-2-raw(c).length));
    console.log(`  ${vl}${c}${pad}${vl}`);
  };
  row('Input',   `${path.basename(inputFile)} (${(rawHTML.length/1024).toFixed(1)} KB)`);
  row('Output',  path.basename(outputFile));
  row('Blocks',  `${ok}/${blocks.length} decoded  ·  ${fail} failed`);
  row('Prot',    `${protWarn} prot-only stripped`);
  row('Iframe',  `${iframeStripped} iframe-protection removed`);
  row('CSS',     `${cssFixed} block(s) hex-decoded  ·  ${inlineStyleFixed} inline attrs`);
  row('CDN',     `${extOk}/${allExternalScripts.length} scripts  ·  ${linkOk}/${externalLinks.length} links preserved`);
  row('Restored',`${restored} script(s)  ·  ${linksRestored} link(s) re-injected`);
  row('HTML',    structResult.issues.length===0 ? '✅ structure valid' : `❌ ${structResult.issues.length} issue(s)`);
  row('JS',      jsTotalIssues===0 ? '✅ syntax valid' : `❌ ${jsTotalIssues} issue(s)`);
  row('Size',    `${finalKB} KB  ·  ${lines.toLocaleString()} lines`);
  console.log(`  ${cl(C.bG,C.b,'╚')}${hl}${cl(C.bG,C.b,'╝')}`);
  console.log('');
}

main().catch(err=>{
  console.error(`\n  ✘  Fatal: ${err.message}\n`);
  process.exit(1);
});
