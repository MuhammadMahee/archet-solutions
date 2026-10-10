'use strict';
(() => {
  const columns = [['dealer','Dealer'],['market','Market'],['store','Store'],['new_activation','New activation'],['upgrade','Upgrade'],['reactivation','Reactivation'],['bts','BTS'],['hsi','HSI'],['accessory','Accessory'],['apo','APO'],['total_boxes','Total boxes'],['qpay','QPay'],['qpay_conv','QPay conv']];
  const themes = {'': ['#095570','#f3f8fa','#083c51','#829aa5'],Connect:['#095570','#f3f8fa','#083c51','#829aa5'],California:['#a92d49','#faf0f2','#491c2c','#ecd8de'],SRH:['#a06118','#fbf5ea','#503718','#e8dcc9'],AMQ:['#365cad','#eef2fa','#20335b','#d6dfef'],ARM:['#176b56','#edf8f3','#104735','#cee7dc'],ARBF:['#7646a5','#f5effa','#3d2652','#e4d7ed']};
  const dateLabel = day => new Date(day + 'T12:00:00').toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'});
  const text = (key,value) => value === null ? '—' : ['accessory','apo'].includes(key) ? '$' + Number(value || 0).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}) : key === 'qpay_conv' ? Number(value || 0).toFixed(0) + '%' : String(value ?? '');
  function reportTitle(result, location='ALL MARKETS') {
    const period=result.start===result.end?dateLabel(result.start):dateLabel(result.start)+' – '+dateLabel(result.end);
    return ('SALES UPDATE • '+location+' • '+period).toUpperCase();
  }
  // Draw a crisp vector-style report, then copy it as a high-resolution PNG.
  function snapshot(data, filters = {}) {
    const cols=columns.filter(([key])=>key!=='dealer'),rows=data.rows;
    const widths=[142,401,241,145,208,80,75,167,126,192,99,172];
    const width=2112,pad=32,tableWidth=2048,tableY=164,rowHeight=52,headerHeight=54,totalHeight=60;
    const incomplete=data.coverage.complete<data.coverage.expected || rows.some(r=>r.incomplete||r.stale);
    const tableHeight=headerHeight+rows.length*rowHeight+totalHeight;
    const height=tableY+tableHeight+64+(incomplete?30:0);
    const canvas=document.createElement('canvas');
    const scale=Math.min(1920/width,15000/height);
    canvas.width=Math.round(width*scale);canvas.height=Math.ceil(height*scale);
    const ctx=canvas.getContext('2d');
    ctx.fillStyle='#f0f5f9';ctx.fillRect(0,0,canvas.width,canvas.height);
    ctx.scale(scale,scale);
    const colors=themes[filters.dealer || '']||themes[''];
    const ink='#16354a',grid='#e0e8ef';
    // Fit the entire table once, so headings, values and totals share one size.
    let tableFont=22;
    ctx.font='700 22px Arial, sans-serif';
    cols.forEach(([key,heading],i)=>{
      const values=[heading.toUpperCase(),...rows.map(row=>text(key,row[key])+(key==='store'&&(row.stale||row.incomplete)?' †':''))];
      if(i>1)values.push(text(key,data.totals[key]));
      for(const value of values){const measured=ctx.measureText(value).width;if(measured)tableFont=Math.min(tableFont,22*(widths[i]-32)/measured);}
    });
    tableFont=Math.floor(tableFont*2)/2;
    function rounded(x,y,w,h,r,fill){ctx.beginPath();ctx.roundRect(x,y,w,h,r);ctx.fillStyle=fill;ctx.fill();}
    function raisedCell(x,y,w,h,fill,dark=false){
      ctx.save();
      ctx.shadowColor=dark?'#00000099':'#15334f70';
      ctx.shadowBlur=6*scale;ctx.shadowOffsetX=1*scale;ctx.shadowOffsetY=4*scale;
      ctx.fillStyle=fill;ctx.fillRect(x,y,w,h);
      ctx.restore();
      // A translucent top reflection leaves the base performance color visible.
      const shine=ctx.createLinearGradient(x,y+2,x,y+h*.46);
      shine.addColorStop(0,dark?'#ffffff4d':'#ffffff85');
      shine.addColorStop(.6,dark?'#ffffff18':'#ffffff30');
      shine.addColorStop(1,'#ffffff00');
      ctx.fillStyle=shine;ctx.fillRect(x+2,y+2,w-4,h*.46-2);
      // Beveled edges create depth without changing the performance fill color.
      const bevel=ctx.createLinearGradient(x,y,x,y+h);
      bevel.addColorStop(0,dark?'#ffffff55':'#ffffffee');
      bevel.addColorStop(.45,dark?'#ffffff10':'#ffffff40');
      bevel.addColorStop(1,dark?'#00000055':'#16354a30');
      ctx.strokeStyle=bevel;ctx.lineWidth=1.5;
      ctx.strokeRect(x+.75,y+.75,w-1.5,h-1.5);
    }
    function label(value,x,y,w,h,font=23,color=ink,align='center',weight=700,fit=true){
      ctx.save();ctx.beginPath();ctx.rect(x+8,y,w-16,h);ctx.clip();
      ctx.fillStyle=color;ctx.textAlign=align;ctx.textBaseline='middle';
      let size=font;ctx.font=weight+' '+size+'px Arial, sans-serif';
      while(fit&&ctx.measureText(value).width>w-28&&size>12){size--;ctx.font=weight+' '+size+'px Arial, sans-serif';}
      ctx.fillText(value,align==='left'?x+16:x+w/2,y+h/2);ctx.restore();
    }
    ctx.fillStyle='#f0f5f9';ctx.fillRect(0,0,width,height);
    // Flat geometric decoration stays away from the text and live figures.
    rounded(pad,24,tableWidth,116,20,colors[2]);
    ctx.save();ctx.beginPath();ctx.roundRect(pad,24,tableWidth,116,20);ctx.clip();
    ctx.fillStyle=colors[0];ctx.beginPath();ctx.moveTo(width-570,24);ctx.lineTo(width-400,140);ctx.lineTo(width,140);ctx.lineTo(width,24);ctx.closePath();ctx.fill();
    ctx.strokeStyle='#ffffff12';ctx.lineWidth=2;
    for(let n=0;n<4;n++){ctx.beginPath();ctx.moveTo(width-620+n*80,24);ctx.lineTo(width-450+n*80,140);ctx.stroke();}
    ctx.restore();
    label(reportTitle(data, filters.market || 'ALL MARKETS'),pad+16,42,tableWidth-260,48,32,'#fff','left',800);
    label('STORE PERFORMANCE  /  '+(incomplete?'PARTIAL DATA':'SALES REPORT'),pad+16,90,tableWidth-260,26,14,'#d9e8f0','left',600);
    rounded(width-pad-190,53,160,56,12,'#ffffff18');
    label(rows.length+' STORES',width-pad-190,53,160,56,22,'#fff');
    rounded(pad,tableY,tableWidth,tableHeight,16,'#fff');
    ctx.save();ctx.beginPath();ctx.roundRect(pad,tableY,tableWidth,tableHeight,16);ctx.clip();
    function drawRow(values,y,kind){
      const head=kind==='head',total=kind==='total',h=total?totalHeight:rowHeight;
      ctx.fillStyle=head?colors[0]:total?colors[2]:kind%2?'#f7fafc':'#fff';
      ctx.fillRect(pad,y,tableWidth,head?headerHeight:h);
      let x=pad;
      cols.forEach(([key,heading],i)=>{
        if(total&&i===0){raisedCell(x+5,y+6,widths[0]+widths[1]-10,h-12,colors[2],true);label('TOTAL',x,y,widths[0]+widths[1],h,tableFont,'#fff','left',700,false);x+=widths[0];return;}
        if(total&&i===1){x+=widths[1];return;}
        const value=values[key];
        const fill=head?colors[0]:total?colors[2]:data.metric_fills?.[kind]?.[key] || (key==='total_boxes'&&value!==null?'#d9edf7':kind%2?'#f7fafc':'#fff');
        raisedCell(x+5,y+6,widths[i]-10,(head?headerHeight:h)-12,fill,head||total);
        const valueText=head?heading.toUpperCase():text(key,value)+(key==='store'&&(values.stale||values.incomplete)?' †':'');
        label(valueText,x,y,widths[i],head?headerHeight:h,tableFont,head||total?'#fff':key==='market'?colors[0]:ink,i===1&&!head?'left':'center',700,false);
        x+=widths[i];
      });
      if(!head&&!total&&(kind===0||rows[kind-1].market!==values.market)){ctx.fillStyle=colors[0];ctx.fillRect(pad,y,4,h);}
    }
    drawRow({},tableY,'head');rows.forEach((r,i)=>drawRow(r,tableY+headerHeight+i*rowHeight,i));
    drawRow(data.totals,tableY+headerHeight+rows.length*rowHeight,'total');
    ctx.restore();ctx.beginPath();ctx.roundRect(pad,tableY,tableWidth,tableHeight,16);ctx.strokeStyle=grid;ctx.lineWidth=1.5;ctx.stroke();
    const footerY=tableY+tableHeight+14;
    label('ARCHET  /  SALES UPDATE',pad,footerY,480,30,14,'#61798b','left',700);
    const legend=ctx.createLinearGradient(width-500,0,width-388,0);legend.addColorStop(0,'#e98181');legend.addColorStop(.5,'#eeee88');legend.addColorStop(1,'#80e77f');
    rounded(width-500,footerY+10,112,10,5,legend);
    label('APO / QPAY CONV  ·  LOW → HIGH',width-380,footerY,348,30,14,'#61798b','left',600);
    if(incomplete)label('† Partial or retained source data. Totals reflect available values.',pad,footerY+30,tableWidth,26,15,'#865c20','left',600);
    return canvas;
  }
  window.salesSnapshot = {render: snapshot};
})();
