let currentJob=null;
const $=x=>document.getElementById(x);
async function jsonOrError(r){let d=await r.json();if(!r.ok)throw Error(d.detail||"Request failed");return d;}
$("analyze").onclick=async()=>{
 const f=$("video").files[0]; if(!f){$("status").textContent="Choose your video file first.";return;}
 $("analyze").disabled=true;$("status").textContent="Uploading video…";
 $("clips").innerHTML="";$("downloads").innerHTML="";$("export").hidden=true;
 try{
  const fd=new FormData();fd.append("video",f);fd.append("source_url",$("url").value);
  if($("sub").files[0])fd.append("transcript",$("sub").files[0]);
  const d=await jsonOrError(await fetch("/api/analyze",{method:"POST",body:fd}));currentJob=d.job_id;
  $("status").textContent="Upload complete. Analysing…";
  let job;
  for(let i=0;i<180;i++){await new Promise(r=>setTimeout(r,2000));job=await jsonOrError(await fetch(`/api/jobs/${currentJob}`));if(job.status!=="analysing")break;$("status").textContent="Analysing video… please wait.";}
  if(job.status!=="ready")throw Error(job.message||"Analysis failed");
  $("status").textContent=job.message;render(job.clips);
 }catch(e){$("status").textContent="Error: "+e.message;}
 finally{$("analyze").disabled=false;}
};
function render(clips){
 $("total").textContent=`${clips.length} SUGGESTIONS`;
 if(!clips.length){$("clips").innerHTML='<div class="empty">No moments found. Try adding an SRT/VTT transcript.</div>';return;}
 $("clips").innerHTML=clips.map(c=>`<article class="clip"><h3>${esc(c.title)}</h3><div class="time">${fmt(c.start)} – ${fmt(c.end)} · ${Math.round(c.end-c.start)} sec</div><p>${esc(c.reason||"Suggested video segment")}</p><div class="score">${c.score==null?"Review candidate":`AI moment score: ${c.score}/100`}</div><label><input type="checkbox" value="${c.id}" checked> Select this clip</label></article>`).join("");
 $("export").hidden=false;
}
function esc(s){return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}
function fmt(n){n=Math.floor(n);return `${Math.floor(n/60)}:${String(n%60).padStart(2,"0")}`;}
$("export").onclick=async()=>{
 const ids=[...document.querySelectorAll('#clips input:checked')].map(x=>x.value);if(!ids.length){$("status").textContent="Select at least one clip.";return;}
 $("export").disabled=true;$("status").textContent="Rendering MP4 files…";
 try{const d=await jsonOrError(await fetch(`/api/jobs/${currentJob}/export`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({clip_ids:ids})}));
 $("downloads").innerHTML="<h3>Your Shorts are ready</h3>"+d.exports.map(x=>`<a href="${x.url}" download>⬇ Download ${esc(x.title)}</a>`).join("");
 $("status").textContent="Export complete.";
 }catch(e){$("status").textContent="Export error: "+e.message;}finally{$("export").disabled=false;}
};