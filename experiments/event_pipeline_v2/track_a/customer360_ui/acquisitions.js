"use strict";
let activeView="profile", eventMonth=null, acquisitionSummary=null, acquisitionSummaryPromise=null;
let acquisitionVersion=0, acquisitionPage=1, acquisitionPages=1, acquisitionFilterTimer;

function updateDashboardLocation() {
  if(!metadata)return;
  const args=new URLSearchParams({month:$("month").value,window:selectedWindow(),preset:$("window").value});
  if(customerId!=null)args.set("id",String(customerId));
  if(eventMonth)args.set("event_month",eventMonth);
  if(activeView==="acquisitions")args.set("view","acquisitions");
  history.replaceState(null,"",`/?${args}`);
}
function showDashboardView(view) {
  activeView=view;
  $("customer-view").hidden=view!=="profile";$("acquisition-view").hidden=view!=="acquisitions";
  for(const [id,selected] of [["tab-profile",view==="profile"],["tab-acquisitions",view==="acquisitions"]]){$(id).setAttribute("aria-selected",String(selected));$(id).tabIndex=selected?0:-1;}
  $("aside-view-label").textContent=view==="profile"?"◎  Hồ sơ khách hàng":"↗  Mở sản phẩm theo tháng";
  if($("products-dialog").open)$("products-dialog").close();
  $("back-to-acquisitions").hidden=!eventMonth;
  if(eventMonth)$("back-to-acquisitions").textContent=`← Trở lại lượt mở tháng ${eventMonth}`;
}
function acquisitionStatus(text,error=false){$("acquisition-status").textContent=text;$("acquisition-status").setAttribute("role",error?"alert":"status");}
function renderMonthIndex() {
  $("acquisition-months").replaceChildren(...acquisitionSummary.months.slice().reverse().map(s=>{
    const row=el("tr"),cell=el("td"),button=el("button",s.month,"month-link");button.type="button";button.setAttribute("aria-label",`Xem lượt mở tháng ${s.month}`);button.setAttribute("aria-pressed",String(s.month===eventMonth));button.addEventListener("click",()=>loadAcquisitions(s.month,1,true));cell.append(button);row.append(cell,el("td",fmt(s.customers_opened)),el("td",fmt(s.product_openings)));return row;
  }));
}
async function ensureAcquisitionSummary() {
  if(!acquisitionSummary){
    if(!acquisitionSummaryPromise)acquisitionSummaryPromise=api("/api/acquisitions/summary").catch(e=>{acquisitionSummaryPromise=null;throw e;});
    acquisitionSummary=await acquisitionSummaryPromise;
  }
  renderMonthIndex();
}
async function openEventCustomer(id,month) {
  showDashboardView("profile");$("month").value=month;syncRange();
  await loadProfile(id);
  if(profile && profile.customer_id===id && profile.as_of_month===month)$("profile").scrollIntoView({behavior:"smooth",block:"start"});
}
async function loadAcquisitions(month,page=1,focus=false) {
  if(!metadata.months.includes(month))return;
  if(month!==eventMonth)$("acquisition-query").value="";
  eventMonth=month;const version=++acquisitionVersion,query=$("acquisition-query").value.trim();
  if(query && !/^\d{1,12}$/.test(query)){acquisitionStatus("Mã khách lọc phải là chữ số, tối đa 12 ký tự.",true);return;}
  $("acquisition-month-title").textContent=`Tháng ${month}`;
  $("acquisition-customers").replaceChildren();$("acquisition-metrics").replaceChildren();$("acquisition-page").textContent="";$("acquisition-note").textContent="";
  $("acquisition-prev").disabled=true;$("acquisition-next").disabled=true;acquisitionStatus(`Đang đọc lượt mở tháng ${month}…`);
  if(acquisitionSummary)renderMonthIndex();
  try {
    const result=await api(`/api/acquisitions?${new URLSearchParams({month,q:query,page,page_size:25})}`);
    if(version!==acquisitionVersion)return;
    const s=result.summary;acquisitionPage=result.page;acquisitionPages=result.total_pages;
    $("acquisition-metrics").replaceChildren(metric("KHÁCH CÓ MỞ THÊM",fmt(s.customers_opened),"Toàn bộ tháng đã chọn"),metric("LƯỢT MỞ SẢN PHẨM",fmt(s.product_openings),"Một khách có thể mở nhiều SP"),metric("KHÁCH SO SÁNH ĐƯỢC",fmt(s.eligible_pairs),`Cặp snapshot ${s.previous_month} → ${s.month}`));
    $("acquisition-note").textContent=`${s.note} ${s.available ? "Có "+fmt(s.unverified_customers)+" khách trong snapshot tháng này chưa đủ cặp dữ liệu để xác định lượt mở." : ""}`;
    const rows=result.rows.map(r=>{const row=el("tr"),customer=el("td"),button=el("button",`#${r.customer_id} ↗`,"month-link");button.type="button";button.setAttribute("aria-label",`Mở hồ sơ khách ${r.customer_id} tại ${month}`);button.addEventListener("click",()=>openEventCustomer(r.customer_id,month));customer.append(button);const products=el("td"),chips=el("div",null,"event-products");for(const p of r.products){const chip=el("span",p.name,"chip");chip.title=p.code;chips.append(chip);}products.append(chips);row.append(customer,el("td",fmt(r.opening_count)),products);return row;});
    if(!rows.length){const row=el("tr"),cell=el("td",!s.available?s.note:query?"Không có khách khớp mã lọc trong tháng này.":"Không ghi nhận lượt mở từ các cặp snapshot đầy đủ.","event-empty");cell.colSpan=3;row.append(cell);rows.push(row);}
    $("acquisition-customers").replaceChildren(...rows);
    const start=result.total_customers?(result.page-1)*result.page_size+1:0,end=Math.min(result.page*result.page_size,result.total_customers);
    $("acquisition-page").textContent=`${fmt(start)}–${fmt(end)} / ${fmt(result.total_customers)} khách${query?" khớp mã lọc":""} · Trang ${result.page}/${result.total_pages}`;
    $("acquisition-prev").disabled=result.page<=1;$("acquisition-next").disabled=result.page>=result.total_pages;
    acquisitionStatus(`Đã tải tháng ${month}. Bấm mã khách để xem hồ sơ tại tháng này.`);updateDashboardLocation();
    if(focus)$("acquisition-detail").scrollIntoView({behavior:"smooth",block:"start"});
  } catch(e){if(version===acquisitionVersion)acquisitionStatus(e.message,true);}
}
async function activateDashboardView(view) {
  showDashboardView(view);
  if(view==="acquisitions"){
    try{await ensureAcquisitionSummary();await loadAcquisitions(eventMonth || $("month").value || metadata.latest_month);}
    catch(e){acquisitionStatus("Không tải được dữ liệu lượt mở: "+e.message,true);}
  }else if(!profile){await loadProfile(customerId || metadata.examples[0]?.customer_id);}
  updateDashboardLocation();
}
async function initializeAcquisitionView(args) {
  const tabs=[$("tab-profile"),$("tab-acquisitions")];tabs.forEach((tab,i)=>{tab.disabled=false;tab.addEventListener("click",()=>activateDashboardView(i?"acquisitions":"profile"));tab.addEventListener("keydown",e=>{if(e.key==="ArrowLeft"||e.key==="ArrowRight"){e.preventDefault();tabs[1-i].focus();tabs[1-i].click();}});});
  $("back-to-acquisitions").addEventListener("click",()=>activateDashboardView("acquisitions"));
  $("choose-another-month").addEventListener("click",()=>$("month-index").scrollIntoView({behavior:"smooth",block:"start"}));
  $("acquisition-filter").addEventListener("submit",e=>{e.preventDefault();clearTimeout(acquisitionFilterTimer);loadAcquisitions(eventMonth,1);});
  $("acquisition-query").addEventListener("input",()=>{clearTimeout(acquisitionFilterTimer);acquisitionFilterTimer=setTimeout(()=>loadAcquisitions(eventMonth,1),250);});
  $("acquisition-prev").addEventListener("click",()=>{if(acquisitionPage>1)loadAcquisitions(eventMonth,acquisitionPage-1);});
  $("acquisition-next").addEventListener("click",()=>{if(acquisitionPage<acquisitionPages)loadAcquisitions(eventMonth,acquisitionPage+1);});
  if(metadata.months.includes(args.get("event_month")))eventMonth=args.get("event_month");
  if(args.get("view")==="acquisitions"){
    if(/^\d{1,12}$/.test(args.get("id")||"")){customerId=Number(args.get("id"));$("customer").value=String(customerId);}
    await activateDashboardView("acquisitions");return true;
  }
  showDashboardView("profile");return false;
}
