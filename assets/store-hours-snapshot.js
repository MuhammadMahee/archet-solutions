'use strict';
(() => {
  const columns = [['date','Date'],['market','Market'],['store','Store'],['employee','Employee'],['store_status','Opening Status'],['opening_time','Opening Time'],['camera_in','Camera In View'],['rt_clockin','RT Clockin'],['opening_status','Opening Status'],['closing_time','Closing Time'],['camera_out','Camera Out View'],['rt_clockout','RT Clockout'],['closing_status','Closing Status'],['chargeback','Late Opening Chargeback']];
  const themes = {'':['#095570','#083c51'],Connect:['#095570','#083c51'],California:['#a92d49','#491c2c'],SRH:['#a06118','#503718'],AMQ:['#365cad','#20335b'],ARM:['#176b56','#104735'],ARBF:['#7646a5','#3d2652']};
  const dateLabel = value => new Date(value+'T12:00:00').toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'});
  function text(key,value) {
    if(key==='chargeback')return value===null?'Pending':value<0?'-$10':'$0';
    if(['opening_time','closing_time','camera_in','camera_out','rt_clockin','rt_clockout'].includes(key)){
      if(!value)return key==='rt_clockin'?'No Clock In':key==='rt_clockout'?'No Clock Out':'—';
      const [h,m,s='00']=(value.includes('T')?value.split('T')[1]:value).split(':');
      return `${Number(h)%12||12}:${m}:${s.slice(0,2)} ${Number(h)>=12?'PM':'AM'}`;
    }
    return key==='date'?dateLabel(value):String(value??'');
  }
  function tone(key,value){
    if(value==='Late'||value==='Early'||(key==='chargeback'&&value===-10))return 'bad';
    if(value==='Open'||value==='On Time')return 'good';
    if(value==='Pending camera review'||value==='Schedule required'||(key==='chargeback'&&value===null))return 'wait';
    if(['rt_clockin','rt_clockout'].includes(key)&&!value)return 'missing';
    return '';
  }
  function render(data,filters={}){
    if(data.rows.length>500)throw new Error('Choose a smaller date range or store filter to copy up to 500 rows in one readable snapshot. Excel includes all filtered rows.');
    const widths=[150,150,310,270,210,142,150,150,210,142,150,150,210,250];
    const tableWidth=widths.reduce((a,b)=>a+b,0),pad=32,width=tableWidth+64,top=164,head=54,rowHeight=44;
    const tableHeight=head+data.rows.length*rowHeight,height=top+tableHeight+94;
    const canvas=document.createElement('canvas'),scale=Math.min(1920/width,15000/height);
    canvas.width=Math.round(width*scale);canvas.height=Math.ceil(height*scale);
    const ctx=canvas.getContext('2d');ctx.scale(scale,scale);
    const theme=themes[filters.dealer||'']||themes[''];
    const rounded=(x,y,w,h,r,fill)=>{ctx.beginPath();ctx.roundRect(x,y,w,h,r);ctx.fillStyle=fill;ctx.fill();};
    function label(value,x,y,w,h,font=19,color='#16354a',align='center'){
      ctx.save();ctx.beginPath();ctx.rect(x+7,y,w-14,h);ctx.clip();ctx.fillStyle=color;ctx.textAlign=align;ctx.textBaseline='middle';
      ctx.font=`700 ${font}px Arial, sans-serif`;
      while(ctx.measureText(value).width>w-22&&font>10){font--;ctx.font=`700 ${font}px Arial, sans-serif`;}
      ctx.fillText(value,align==='left'?x+12:x+w/2,y+h/2);ctx.restore();
    }
    // Same banner, dealer palette, raised cells and PNG export treatment as Sales Update.
    function raised(x,y,w,h,fill,dark=false){
      ctx.save();ctx.shadowColor=dark?'#00000099':'#15334f70';ctx.shadowBlur=6*scale;ctx.shadowOffsetX=scale;ctx.shadowOffsetY=4*scale;ctx.fillStyle=fill;ctx.fillRect(x,y,w,h);ctx.restore();
      const shine=ctx.createLinearGradient(x,y+2,x,y+h*.46);shine.addColorStop(0,dark?'#ffffff4d':'#ffffff85');shine.addColorStop(1,'#ffffff00');ctx.fillStyle=shine;ctx.fillRect(x+2,y+2,w-4,h*.46-2);
      const bevel=ctx.createLinearGradient(x,y,x,y+h);bevel.addColorStop(0,dark?'#ffffff55':'#ffffffee');bevel.addColorStop(1,dark?'#00000055':'#16354a30');ctx.strokeStyle=bevel;ctx.lineWidth=1.5;ctx.strokeRect(x+.75,y+.75,w-1.5,h-1.5);
    }
    ctx.fillStyle='#f0f5f9';ctx.fillRect(0,0,width,height);
    rounded(pad,24,tableWidth,116,20,theme[1]);ctx.save();ctx.beginPath();ctx.roundRect(pad,24,tableWidth,116,20);ctx.clip();
    ctx.fillStyle=theme[0];ctx.beginPath();ctx.moveTo(width-570,24);ctx.lineTo(width-400,140);ctx.lineTo(width,140);ctx.lineTo(width,24);ctx.closePath();ctx.fill();ctx.restore();
    const period=data.start===data.end?dateLabel(data.start):`${dateLabel(data.start)} – ${dateLabel(data.end)}`;
    label(`STORE OPENING / CLOSING • ${filters.market||'ALL MARKETS'} • ${period}`.toUpperCase(),pad+16,42,tableWidth-290,48,32,'#fff','left');
    label('CAMERA REVIEW  /  STORE OPERATIONS',pad+16,90,tableWidth-260,26,14,'#d9e8f0','left');
    rounded(width-pad-220,53,190,56,12,'#ffffff18');label(`${data.rows.length} RECORDS`,width-pad-220,53,190,56,22,'#fff');
    rounded(pad,top,tableWidth,tableHeight,14,'#fff');
    ctx.save();ctx.beginPath();ctx.roundRect(pad,top,tableWidth,tableHeight,14);ctx.clip();
    function draw(row,n){
      const isHead=n<0,y=isHead?top:top+head+n*rowHeight,h=isHead?head:rowHeight;
      ctx.fillStyle=isHead?theme[0]:n%2?'#f7fafc':'#fff';ctx.fillRect(pad,y,tableWidth,h);
      let x=pad;
      columns.forEach(([key,heading],i)=>{
        const state=isHead?'':tone(key,row[key]);
        const fill=isHead?theme[0]:({good:'#c6efce',bad:'#ffc7ce',wait:'#fff2d5'}[state]||(n%2?'#f7fafc':'#fff'));
        raised(x+4,y+5,widths[i]-8,h-10,fill,isHead);
        label(isHead?heading.toUpperCase():text(key,row[key]),x,y,widths[i],h,isHead?17:19,isHead?'#fff':state==='missing'||state==='bad'?'#ad1d32':'#16354a',i===2&&!isHead?'left':'center');
        x+=widths[i];
      });
    }
    draw({},-1);data.rows.forEach(draw);ctx.restore();
    label('ARCHET  /  STORE OPENING & CLOSING',pad,top+tableHeight+12,650,28,14,'#61798b','left');
    const amount=data.rows.reduce((sum,r)=>sum+(r.chargeback||0),0);
    label(`ASSESSED CHARGEBACKS: ${amount<0?'-$'+Math.abs(amount):'$0'}   •   GREEN: ON TIME   /   RED: LATE OR EARLY   /   AMBER: PENDING`,width-1600,top+tableHeight+12,1568,28,14,'#61798b');
    label(`SOURCE COVERAGE: ${data.coverage.complete}/${data.coverage.expected} ACCOUNT-DAYS. Missing camera or scheduled times remain pending.`,pad,top+tableHeight+43,tableWidth,26,14,'#865c20','left');
    return canvas;
  }
  window.storeHoursSnapshot={render,columns,text,tone};
})();
