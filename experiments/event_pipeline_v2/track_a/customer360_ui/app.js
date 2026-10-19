"use strict";
const $ = id => document.getElementById(id);
const el = (tag, text, cls) => { const n = document.createElement(tag); if (text != null) n.textContent = text; if (cls) n.className = cls; return n; };
const fmt = (v, digits = 0) => v == null ? "—" : Number(v).toLocaleString("vi-VN", { maximumFractionDigits: digits, minimumFractionDigits: digits });
let metadata, profile, customerId, requestVersion = 0, searchVersion = 0, timer;
async function api(path) { const r = await fetch(path, { cache: "no-store" }); const body = await r.json(); if (!r.ok) throw new Error(body.error || "Không đọc được dữ liệu"); return body; }
function status(text, error = false) { $("status").textContent = text; $("status").setAttribute("role", error ? "alert" : "status"); }
function pill(label) { return el("span", label, "pill" + (label === "At-risk" ? " risk" : label === "Churned" ? " dead" : "")); }
function metric(label, value, hint) { const n = el("div", null, "metric"); n.append(el("div", label, "label"), el("div", value, "value"), el("div", hint, "hint")); return n; }
function showProducts(snapshot) {
  if(!profile || !snapshot.product_complete || !snapshot.is_observed)return;
  const dialog=$("products-dialog"), owned=snapshot.owned || [];
  $("products-context").textContent=`Khách #${profile.customer_id} · Tháng ${snapshot.month} · ${owned.length} sản phẩm`;
  $("products-list").replaceChildren(...owned.map((code,i)=>{const item=el("li");item.append(el("span",String(i+1).padStart(2,"0"),"product-number"),el("span",profile.product_names[code] || code));if((snapshot.acquired||[]).includes(code))item.append(el("span","Mới ghi nhận","product-new"));return item;}));
  $("products-note").textContent=owned.length ? "Danh sách lấy từ snapshot của tháng đã chọn. “Mới ghi nhận” là thay đổi từ không sở hữu sang sở hữu so với tháng liền trước có dữ liệu đầy đủ." : "Snapshot tháng này ghi nhận 0 sản phẩm đang sở hữu.";
  if(!dialog.open)dialog.showModal();
}
function syncRange(preferredStart) {
  const end = metadata.months.indexOf($("month").value);
  const available = metadata.months.slice(Math.max(0,end-23),end+1);
  const previous = preferredStart || $("start-month").value;
  $("start-month").replaceChildren(...available.slice().reverse().map(m=>{const o=el("option",m);o.value=m;return o;}));
  const preset = $("window").value;
  $("start-month").value = preset === "custom" ? (available.includes(previous) ? previous : available[available.length-1]) : available[Math.max(0,available.length-Number(preset))];
}
function selectedWindow() { return metadata.months.indexOf($("month").value)-metadata.months.indexOf($("start-month").value)+1; }
function renderPersona(p) {
  const c=p.current, own=p.customer_demographics, blocks=[];
  const info=el("div",null,"persona-block");info.append(el("h3","Thông tin khách hàng"),el("p",`Ghi nhận tại ${p.as_of_month}; ${c.is_observed ? "dữ liệu của chính khách hàng" : "khách vắng trong snapshot tháng này"}.`,"small"));
  const table=el("table",null,"customer-info-table"),body=el("tbody");
  for(const [label,value] of [["Tuổi",own.age==null?"Chưa có dữ liệu":fmt(own.age)],["Thu nhập (renta)",own.income==null?"Chưa có dữ liệu":fmt(own.income)],["Thâm niên",own.tenure==null?"Chưa có dữ liệu":fmt(own.tenure)+" tháng"],["Kênh vào",own.channel||"Chưa có dữ liệu"],["Phân khúc",own.segment||"Chưa có dữ liệu"]]){const row=el("tr");row.append(el("th",label),el("td",value));body.append(row);}
  table.append(body);info.append(table);blocks.push(info);
  const rule=el("div",null,"persona-block");rule.append(el("h3",`${c.persona_rule || "Nhãn P chưa khả dụng"} · Nhóm theo quy tắc hành vi`));
  rule.append(el("p",p.persona_description,"small"));
  const rules={P1:["F = 0","Số SP ≤ 2"],P2:["F = 0","Số SP ≥ 3"],P3:["F = 1"],P4:["F ≥ 2","Số SP ≤ 1"],P5:["F ≥ 2","2 ≤ số SP ≤ 4"],P6:["F ≥ 2","Số SP ≥ 5"]};
  if(rules[c.persona_rule]) {
    const list=el("ul",null,"persona-rules");
    list.append(el("li",`Quy tắc: ${rules[c.persona_rule].join(" và ")}.`));
    list.append(el("li",`Dữ liệu khách: F=${fmt(c.F)} tháng có mở thêm SP; danh mục hiện tại=${fmt(c.n_products)} sản phẩm.`));
    list.append(el("li",`Lịch sử có ${fmt(c.observed_pairs)} cặp tháng đầy đủ. F tính đến ${p.as_of_month}, không tính lại theo khoảng biểu đồ.`));rule.append(list);
  }
  blocks.push(rule,el("p",`Thông tin khách và nhóm hành vi P lấy tại tháng chấm điểm. Đổi khoảng xem chỉ đổi lịch sử hiển thị; đổi tháng chấm điểm cập nhật toàn bộ hồ sơ.`,"small"));
  $("persona-explanation").replaceChildren(...blocks);
}
function svgNode(tag, attributes = {}, text) { const n = document.createElementNS("http://www.w3.org/2000/svg", tag); for (const [k,v] of Object.entries(attributes)) n.setAttribute(k, String(v)); if (text != null) n.textContent = text; return n; }
function chart(title, rows, key, digits) {
  const card = el("div", null, "chart"); card.append(el("h3", title));
  const svg = svgNode("svg", { viewBox: "0 0 480 135", role: key==="n_products" ? "group" : "img", "aria-label": title });
  const vals = rows.map(r => r[key]), finite = vals.filter(v => v != null), max = Math.max(...finite, 0.01) * 1.22;
  svg.append(svgNode("line", {x1:25,y1:106,x2:458,y2:106,class:"axis"}));
  let previous = null;
  rows.forEach((row, i) => {
    const x = rows.length === 1 ? 240 : 29 + i * 420 / (rows.length-1), v = vals[i], y = v == null ? null : 105 - v / max * 78;
    if (v != null) {
      if (previous) svg.append(svgNode("line", { x1:previous.x,y1:previous.y,x2:x,y2:y,class:"line" }));
      const point = svgNode("circle", {cx:x,cy:y,r:4}); point.append(svgNode("title", {}, `${row.month}: ${fmt(v,digits)}`));
      if(key==="n_products" && row.product_complete && row.is_observed){point.setAttribute("role","button");point.setAttribute("tabindex","0");point.setAttribute("class","owned-point");point.setAttribute("aria-label",`Xem danh sách sản phẩm trên biểu đồ tháng ${row.month}`);point.addEventListener("click",()=>showProducts(row));point.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();showProducts(row);}});}
      svg.append(point);
      if (rows.length <= 12 || i === 0 || i === rows.length-1) svg.append(svgNode("text", {x,y:y-10,"text-anchor":"middle"}, fmt(v,digits)));
      previous = {x,y};
    } else { previous = null; svg.append(svgNode("text", {x,y:95,"text-anchor":"middle"}, "—")); }
    if (rows.length <= 6 || i % Math.ceil(rows.length/6) === 0 || i === rows.length-1) svg.append(svgNode("text", {x,y:126,"text-anchor":"middle"}, row.month.slice(5)+"/"+row.month.slice(2,4)));
  });
  if (!finite.length) svg.append(svgNode("text", {x:240,y:55,"text-anchor":"middle"}, "Chưa có dữ liệu hợp lệ"));
  card.append(svg); return card;
}
function render(p) {
  const c = p.current;
  $("metric-month").textContent = `Điểm tại tháng ${p.as_of_month} · Khách #${p.customer_id}`;
  $("metric-period-note").textContent = `RFM, CLV, lifecycle và persona bên dưới lấy tại ${p.as_of_month}. Lịch sử đang xem: ${p.timeline[0].month} → ${p.as_of_month}.`;
  $("customer-title").textContent = `Khách hàng #${p.customer_id}`;
  $("profile-subtitle").textContent = `${p.timeline[0].month} → ${p.as_of_month} · ${p.timeline.length} tháng hiển thị · ${c.is_observed ? "Có trong snapshot" : "Vắng trong snapshot"}`;
  renderEventContext(p);
  $("metrics").replaceChildren(
    metric("R / RECENCY", c.R == null ? "—" : `${fmt(c.R)} tháng`, c.rfm_no_event === 1 ? "Chưa ghi nhận sự kiện; không gán R = 0" : "Từ lần mở thêm sản phẩm gần nhất"),
    metric("F / FREQUENCY", fmt(c.F), "Số tháng có mở thêm SP trong lịch sử hợp lệ"),
    metric("M / PROPENSITY", fmt(c.M, 3), `Điểm danh mục tại ${p.as_of_month} · ${c.m_uses_baseline === 1 ? "dùng baseline" : "không phải tiền"}`),
    metric("CLV / 1 THÁNG", fmt(c.clv_1m, 3), `SP mở thêm kỳ vọng cho ${p.forecast_month}`),
    metric("LIFECYCLE", c.lifecycle, c.historical_deceased ? "Có cờ indfall=S trong lịch sử · cần xác minh" : `Theo quan sát & trạng thái khách tại ${p.as_of_month}`)
  );
  $("decision").textContent = p.policy.label;
  $("decision-reason").textContent = p.policy.reasons.join(" ") + (c.clv_peer_percentile == null ? "" : ` Phân vị CLV-proxy: ${fmt(c.clv_peer_percentile,1)}/100 trên ${fmt(c.clv_peer_n)} khách đủ điều kiện cùng tháng.`);
  $("next-step").textContent = p.policy.next_step;
  $("policy-note").textContent = `${p.policy.basis} Chưa thể tính ROI. Policy ${p.policy.policy_version}.`;
  $("persona").textContent = "Thông tin & nhóm hành vi";
  renderPersona(p);
  $("evidence-label").textContent = p.evidence.label;
  $("evidence-note").textContent = `${c.observed_pairs == null ? "Chưa có snapshot đầy đủ ở tháng này" : c.observed_pairs+" cặp tháng đầy đủ trong lịch sử"} · ${p.evidence.gap_months} tháng thiếu/vắng trong cửa sổ. ${p.evidence.meaning}`;
  $("charts").replaceChildren(chart("Số sản phẩm đang sở hữu", p.timeline,"n_products",0), chart("CLV-proxy · SP mở thêm kỳ vọng 1 tháng",p.timeline,"clv_1m",3));
  $("history-body").replaceChildren(...p.timeline.map(r => {
    const tr = el("tr"); const lifecycle = el("td"); lifecycle.append(pill(r.lifecycle));
    const monthCell=el("td"), monthButton=el("button",r.month,"month-link");monthButton.type="button";monthButton.setAttribute("aria-label",`Xem điểm tại ${r.month}`);monthButton.title=`Xem RFM, CLV, lifecycle tại ${r.month}`;
    if(r.known)monthButton.addEventListener("click",()=>{$("month").value=r.month;syncRange();loadProfile(p.customer_id,{focusMetrics:true});});else monthButton.disabled=true;
    if(r.month===p.as_of_month)monthButton.setAttribute("aria-current","date");monthCell.append(monthButton);
    const productsCell=el("td");
    if(r.product_complete && r.is_observed && r.n_products!=null){const b=el("button",fmt(r.n_products),"product-link");b.type="button";b.setAttribute("aria-label",`Xem sản phẩm tháng ${r.month}`);b.title="Bấm để xem danh sách sản phẩm đang sở hữu";b.addEventListener("click",()=>showProducts(r));productsCell.append(b);}else productsCell.textContent="—";
    tr.append(monthCell, lifecycle, el("td",fmt(r.R)), el("td",fmt(r.F)), el("td",fmt(r.M,3)), productsCell, el("td",fmt(r.clv_1m,3)), el("td",r.persona_rule || "—"));
    const changes = el("td",r.acquired == null ? "—" : `+${r.acquired.length} / −${r.removed.length}`);
    changes.title = r.acquired == null ? "Không có cặp tháng liên tiếp đầy đủ" : `Mở: ${r.acquired.map(x=>p.product_names[x]).join(", ") || "0"}; Rời: ${r.removed.map(x=>p.product_names[x]).join(", ") || "0"}`;
    tr.append(changes); return tr;
  }));
  const owned = el("div",null,"chips");
  for (const code of c.owned) { const chip = el("span",p.product_names[code],"chip"); chip.title=code; owned.append(chip); }
  $("owned").replaceChildren(el("p", c.product_complete ? `Đang sở hữu ${c.owned.length} sản phẩm` : "Chưa xác minh được danh mục hiện tại", "small"), owned);
  const recs = p.recommendations.map((r,i) => {
    const n=el("div",null,"recommendation"), body=el("div",null,"rec-main"), meter=el("meter");
    meter.max=p.recommendations[0].score; meter.value=r.score; meter.setAttribute("aria-label",`Affinity ${r.name}: ${r.score}`);
    body.append(el("div",r.name),meter); n.append(el("span",String(i+1).padStart(2,"0"),"rank"),body,el("span",fmt(r.score,4),"rec-score")); n.title=r.product; return n;
  });
  $("recommendations").replaceChildren(...(recs.length ? [el("h3","Top sản phẩm chưa sở hữu"),...recs] : [el("p","Chưa hiển thị đề xuất: kiểm tra điều kiện tiếp cận, lịch sử và điểm affinity hợp lệ.","muted")]));
  $("insights").replaceChildren(...p.insights.map(s=>el("li",s)));
  $("outlook").textContent = c.clv_1m == null ? "Tương lai: chưa đủ cơ sở dự báo cá nhân ở tháng này. Cần cập nhật dữ liệu trước khi ra quyết định." : `Triển vọng gần nhất: mô hình ước lượng ${fmt(c.clv_1m,3)} sản phẩm mở thêm trong ${p.forecast_month}. Đây là kỳ vọng của mô hình, không đảm bảo khách sẽ mua. Chưa có cơ sở kết luận triển vọng lợi nhuận dài hạn.`;
  $("limitations").replaceChildren(...p.limitations.map(s=>el("li",s)));
  $("provenance").textContent = `Nguồn: ${p.source_run} · Scope: ${p.scope} · As-of: ${p.as_of_month} · Không dùng tháng tương lai cho nhận định tại tháng đã chọn.`;
  $("profile").hidden=false;
}
async function loadProfile(id, {focusMetrics=false} = {}) {
  if($("products-dialog").open)$("products-dialog").close();
  const version=++requestVersion; searchVersion++; $("results").replaceChildren(); $("profile").hidden=true;
  status("Đang tổng hợp hồ sơ…"); $("search-form").querySelector("button").disabled=true;
  try {
    const p=await api(`/api/profile?${new URLSearchParams({id,month:$("month").value,window:selectedWindow()})}`);
    if(version!==requestVersion)return;
    profile=p; customerId=p.customer_id; $("customer").value=String(customerId); render(p); status(`Đã tổng hợp hồ sơ #${id} tại ${p.as_of_month}.`);
    if(focusMetrics)$("metric-month").scrollIntoView({behavior:"smooth",block:"start"});
    updateDashboardLocation();
  } catch(e) { if(version===requestVersion) status(e.message,true); }
  finally {if(version===requestVersion) $("search-form").querySelector("button").disabled=false;}
}
$("search-form").addEventListener("submit",e=>{e.preventDefault();loadProfile($("customer").value.trim());});
$("customer").addEventListener("input",()=>{clearTimeout(timer); const version=++searchVersion; const q=$("customer").value.trim(); $("results").replaceChildren(); if(!/^\d{1,12}$/.test(q))return; timer=setTimeout(async()=>{
  try { const rows=await api(`/api/customers?${new URLSearchParams({q,month:$("month").value})}`); if(version!==searchVersion)return; $("results").replaceChildren(...rows.map(r=>{const b=el("button",`#${r.customer_id} · ${r.lifecycle}`);b.type="button";b.addEventListener("click",()=>loadProfile(r.customer_id));return b;})); } catch(e){if(version===searchVersion)status(e.message,true);}
},220);});
for(const id of ["month","window","start-month"]) $(id).addEventListener("change",()=>{searchVersion++;$("results").replaceChildren();if(id==="start-month")$("window").value="custom";else syncRange();if(customerId!=null)loadProfile(customerId,{focusMetrics:id==="month"});});
$("download").addEventListener("click",()=>{if(!profile)return;const url=URL.createObjectURL(new Blob([JSON.stringify(profile,null,2)],{type:"application/json"}));const a=el("a");a.href=url;a.download=`customer-${profile.customer_id}-${profile.as_of_month}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
(async()=>{try{
  metadata=await api("/api/meta"); $("scope").textContent=`${fmt(metadata.customer_count)} khách · ${metadata.months[0]} → ${metadata.latest_month}`;
  $("month").replaceChildren(...metadata.months.slice().reverse().map(m=>{const o=el("option",m);o.value=m;return o;}));
  $("examples").replaceChildren(el("span","Xem nhanh:","small"),...metadata.examples.map(r=>{const b=el("button",`${r.label} #${r.customer_id}`);b.addEventListener("click",()=>{$("month").value=metadata.latest_month;syncRange();loadProfile(r.customer_id);});return b;}));
  const args=new URLSearchParams(location.search);if(metadata.months.includes(args.get("month")))$("month").value=args.get("month");
  const requested=Number(args.get("window")||6), end=metadata.months.indexOf($("month").value);
  $("window").value=["6","12","24","custom"].includes(args.get("preset")) ? args.get("preset") : [6,12,24].includes(requested) ? String(requested) : "custom";
  syncRange(metadata.months[Math.max(0,end-(Number.isInteger(requested)&&requested>=1&&requested<=24?requested:6)+1)]);
  if(await initializeAcquisitionView(args))return;
  if(/^\d{1,12}$/.test(args.get("id")||""))await loadProfile(args.get("id")); else if(metadata.examples.length)await loadProfile(metadata.examples[0].customer_id);
}catch(e){status("Không kết nối được dữ liệu: "+e.message,true);}})();
