using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;
using System.Diagnostics;
using System.Text;
using System.Text.Json;

internal static class Program
{
    [STAThread]
    static int Main(string[] args)
    {
        ApplicationConfiguration.Initialize();
        if (args.Length != 2 || (args[0] != "--profile" && args[0] != "--smoke-test"))
            return 2;
        var smoke = args[0] == "--smoke-test";
        var root = Path.GetFullPath(args[1]);
        Directory.CreateDirectory(root);
        using var window = new EdgeWindow(root, smoke);
        Application.Run(window);
        return window.Result;
    }
}

sealed class EdgeWindow : Form
{
    readonly string root;
    readonly bool smoke;
    readonly TabControl tabs = new() { Dock = DockStyle.Fill };
    readonly TextBox address = new() { Dock = DockStyle.Fill, RightToLeft = RightToLeft.No };
    readonly Label status = new() { Dock = DockStyle.Fill, AutoEllipsis = true, TextAlign = ContentAlignment.MiddleRight };
    readonly Button back = new() { Text = "←" }, forward = new() { Text = "→" }, reload = new() { Text = "↻" };
    readonly Dictionary<string, (string url, TabPage tab)> links = new();
    readonly Dictionary<TabPage, WebView2> views = new();
    readonly StreamWriter? output;
    CoreWebView2Environment? environment;
    bool ready, stopping;
    int nextTab;
    public int Result { get; private set; } = 1;
    WebView2? Current => tabs.SelectedTab is TabPage tab && views.TryGetValue(tab, out var view) ? view : null;

    public EdgeWindow(string profile, bool test)
    {
        root = profile; smoke = test;
        Text = "کافی‌نت جوان | مرورگر Microsoft Edge WebView2";
        WindowState = FormWindowState.Maximized;
        MinimumSize = new Size(850, 520);
        Font = new Font("Segoe UI", 10);
        BackColor = Color.FromArgb(239, 244, 249);
        var toolbar = new TableLayoutPanel { Dock = DockStyle.Top, Height = 47, ColumnCount = 9, Padding = new Padding(7), BackColor = Color.White };
        for (int i=0;i<3;i++) toolbar.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 46));
        toolbar.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        for (int i=4;i<9;i++) toolbar.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, i==8?120:85));
        toolbar.Controls.Add(back,0,0); toolbar.Controls.Add(forward,1,0); toolbar.Controls.Add(reload,2,0);
        toolbar.Controls.Add(address,3,0);
        toolbar.Controls.Add(ActionButton("برو", () => Go()),4,0);
        toolbar.Controls.Add(ActionButton("＋ زبانه", async () => await OpenAsync("", "https://www.bing.com/", "زبانه جدید")),5,0);
        toolbar.Controls.Add(ActionButton("بستن تب", () => CloseTab()),6,0);
        toolbar.Controls.Add(ActionButton("چاپ", () => Current?.CoreWebView2?.ShowPrintUI()),7,0);
        toolbar.Controls.Add(ActionButton("ذخیره PDF", async () => await SavePdf()),8,0);
        back.Click += (_,_) => { if(Current?.CanGoBack==true) Current.GoBack(); };
        forward.Click += (_,_) => { if(Current?.CanGoForward==true) Current.GoForward(); };
        reload.Click += (_,_) => Current?.Reload();
        address.KeyDown += (_,e) => { if(e.KeyCode==Keys.Enter) { e.SuppressKeyPress=true; Go(); } };
        var footer = new TableLayoutPanel { Dock=DockStyle.Bottom, Height=34, ColumnCount=4, BackColor=Color.White };
        footer.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));
        footer.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,80));
        footer.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,80));
        footer.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,140));
        footer.Controls.Add(status,0,0);
        footer.Controls.Add(ActionButton("− بزرگ‌نما",()=>Zoom(-.1)),1,0);
        footer.Controls.Add(ActionButton("+ بزرگ‌نما",()=>Zoom(.1)),2,0);
        footer.Controls.Add(ActionButton("Edge اصلی",()=>OpenFullEdge()),3,0);
        Controls.Add(tabs); Controls.Add(footer); Controls.Add(toolbar);
        tabs.SelectedIndexChanged += (_,_) => Sync();
        if (!smoke)
        {
            output = new StreamWriter(Console.OpenStandardOutput(), new UTF8Encoding(false)) { AutoFlush=true };
        }
        Shown += async (_,_) => await Initialize();
        FormClosing += (_,_) => { stopping=true; Result=smoke?Result:0; };
    }

    Button ActionButton(string title, Action action)
    {
        var b=new Button { Text=title, Dock=DockStyle.Fill, FlatStyle=FlatStyle.Flat, Margin=new Padding(2) };
        b.FlatAppearance.BorderColor=Color.FromArgb(210,220,230);
        b.Click += (_,_) => { try { action(); } catch { status.Text="عملیات انجام نشد."; } };
        return b;
    }
    void Emit(string kind, string text="")
    {
        if(smoke) File.AppendAllText(Path.Combine(root,"edge-smoke.log"),kind+": "+text+Environment.NewLine);
        else
        {
            try { output?.WriteLine(JsonSerializer.Serialize(new { kind, text })); } catch(IOException) { }
        }
    }
    static bool SafeUrl(string? raw) => Uri.TryCreate(raw,UriKind.Absolute,out var uri) &&
        (uri.Scheme==Uri.UriSchemeHttp || uri.Scheme==Uri.UriSchemeHttps) &&
        uri.Host.Length>0 && uri.UserInfo.Length==0;

    async Task Initialize()
    {
        try
        {
            environment=await CoreWebView2Environment.CreateAsync(null,Path.Combine(root,"profile"));
            ready=true;
            Emit("ready",environment.BrowserVersionString);
            if(smoke) { await Smoke(); return; }
            status.Text="مرورگر Edge آماده است.";
            _=ReadCommands();
        }
        catch(Exception ex)
        {
            Emit("error", "WebView2 initialization: "+ex.GetType().Name);
            if(smoke) Close();
            else { status.Text="موتور WebView2 راه‌اندازی نشد."; Close(); }
        }
    }

    async Task ReadCommands()
    {
        try
        {
            using var input = new StreamReader(Console.OpenStandardInput(), Encoding.UTF8);
            while(!stopping)
            {
                var line=await input.ReadLineAsync();
                if(line==null) break;
                try
                {
                    using var doc=JsonDocument.Parse(line);
                    var o=doc.RootElement;
                    var cmd=o.GetProperty("cmd").GetString();
                    if(cmd=="close") break;
                    if(cmd=="open")
                    {
                        var key=o.GetProperty("id").GetString()??"";
                        var url=o.GetProperty("url").GetString()??"";
                        var title=o.GetProperty("title").GetString()??"";
                        await OpenAsync(key,url,title);
                        if(WindowState==FormWindowState.Minimized) WindowState=FormWindowState.Maximized;
                        Activate();
                    }
                }
                catch(Exception ex) { Emit("error","Browser command: "+ex.GetType().Name); }
            }
        }
        catch(IOException) { }
        if(!stopping) Close();
    }

    async Task<WebView2> AddTab(string title)
    {
        var tab=new TabPage(title.Length>50?title[..50]:title);
        var view=new WebView2 { Dock=DockStyle.Fill };
        views.Add(tab,view); tab.Controls.Add(view); tabs.TabPages.Add(tab); tabs.SelectedTab=tab;
        try
        {
            await view.EnsureCoreWebView2Async(environment);
            var core=view.CoreWebView2;
            core.Settings.AreHostObjectsAllowed=false;
            core.Settings.IsWebMessageEnabled=false;
            core.Settings.AreDevToolsEnabled=false;
            core.Profile.IsPasswordAutosaveEnabled=false;
            core.Profile.IsGeneralAutofillEnabled=false;
            core.NavigationStarting += (_,e) =>
            {
                if(!SafeUrl(e.Uri) && e.Uri!="about:blank" && !e.Uri.StartsWith("blob:https://",StringComparison.OrdinalIgnoreCase))
                { e.Cancel=true; status.Text="نشانی خارج از HTTP(S) مسدود شد."; }
                else status.Text="در حال بارگذاری…";
            };
            core.NavigationCompleted += (_,e) =>
            {
                if(tabs.SelectedTab==tab) { Sync(); status.Text=e.IsSuccess?"آماده":("بارگذاری ناموفق: "+e.WebErrorStatus); }
            };
            core.SourceChanged += (_,_)=>{ if(tabs.SelectedTab==tab) Sync(); };
            core.HistoryChanged += (_,_)=>{ if(tabs.SelectedTab==tab) Sync(); };
            core.DocumentTitleChanged += (_,_) =>
            {
                var t=core.DocumentTitle;
                if(!string.IsNullOrWhiteSpace(t)) tab.Text=t.Length>50?t[..50]:t;
            };
            core.ServerCertificateErrorDetected += (_,e)=>e.Action=CoreWebView2ServerCertificateErrorAction.Cancel;
            core.PermissionRequested += (_,e) =>
            {
                e.SavesInProfile=false;
                e.State=CoreWebView2PermissionState.Deny;
                if((e.PermissionKind==CoreWebView2PermissionKind.Camera || e.PermissionKind==CoreWebView2PermissionKind.Microphone)
                   && Uri.TryCreate(e.Uri,UriKind.Absolute,out var u) && u.Scheme=="https")
                {
                    if(MessageBox.Show(this,"دسترسی "+e.PermissionKind+" به "+u.Host+" مجاز باشد؟","تأیید دسترسی",MessageBoxButtons.YesNo,MessageBoxIcon.Question)==DialogResult.Yes)
                        e.State=CoreWebView2PermissionState.Allow;
                }
            };
            core.NewWindowRequested += async (_,e) =>
            {
                var def=e.GetDeferral();
                try
                {
                    e.Handled=true;
                    if(!e.IsUserInitiated || (!SafeUrl(e.Uri) && e.Uri!="about:blank" && !string.IsNullOrEmpty(e.Uri)) || tabs.TabCount>=24)
                    { status.Text="پنجره خودکار مسدود شد."; return; }
                    var child=await AddTab("زبانه جدید");
                    e.NewWindow=child.CoreWebView2;
                }
                catch { status.Text="پنجره جدید باز نشد."; }
                finally { def.Complete(); }
            };
            core.ProcessFailed += (_,e)=> { status.Text="پردازش سایت متوقف شد؛ در صورت نیاز بارگذاری مجدد کنید."; Emit("notice","Renderer: "+e.ProcessFailedKind); };
            core.WindowCloseRequested += (_,_) => CloseTab(tab);
            return view;
        }
        catch
        {
            CloseTab(tab);
            throw;
        }
    }

    async Task<WebView2?> OpenAsync(string key,string url,string title)
    {
        if(!ready || !SafeUrl(url)) return null;
        if(!string.IsNullOrEmpty(key) && links.TryGetValue(key,out var existing) && existing.url==url && views.ContainsKey(existing.tab))
        {
            // Select the live renderer without Navigate/Reload, even after redirects.
            tabs.SelectedTab=existing.tab;
            Sync();
            Emit("reused");
            return views[existing.tab];
        }
        if(tabs.TabCount>=24) { status.Text="حداکثر ۲۴ زبانه"; return null; }
        var view=await AddTab(string.IsNullOrWhiteSpace(title)?"زبانه "+(++nextTab):title);
        var tab=(TabPage)view.Parent!;
        if(!string.IsNullOrEmpty(key)) links[key]=(url,tab);
        view.CoreWebView2.Navigate(url);
        return view;
    }
    void Sync()
    {
        var v=Current;
        if(v?.CoreWebView2==null) return;
        if(!address.Focused) address.Text=v.Source?.ToString()??"";
        back.Enabled=v.CanGoBack; forward.Enabled=v.CanGoForward;
        if(v.Source?.Scheme=="http") status.Text="هشدار: اتصال HTTP رمزنگاری نشده";
    }
    void Go()
    {
        var text=address.Text.Trim();
        if(!text.Contains("://")) text="https://"+text;
        if(!SafeUrl(text)) { status.Text="نشانی معتبر HTTP یا HTTPS وارد کنید."; return; }
        var v=Current;
        if(v?.CoreWebView2==null) { _=OpenAsync("",text,"زبانه جدید"); return; }
        if(Uri.TryCreate(text,UriKind.Absolute,out var requested) && requested==v.Source) return;
        // The tab is no longer identified with its original catalog entry.
        foreach(var k in links.Where(x=>x.Value.tab==tabs.SelectedTab).Select(x=>x.Key).ToArray()) links.Remove(k);
        v.CoreWebView2.Navigate(text);
    }
    void Zoom(double delta) { if(Current is WebView2 v) v.ZoomFactor=Math.Clamp(v.ZoomFactor+delta,.5,2); }
    void CloseTab(TabPage? target=null)
    {
        var tab=target??tabs.SelectedTab;
        if(tab==null) return;
        foreach(var k in links.Where(x=>x.Value.tab==tab).Select(x=>x.Key).ToArray()) links.Remove(k);
        views.Remove(tab); tabs.TabPages.Remove(tab); tab.Dispose();
    }
    async Task SavePdf()
    {
        var v=Current;
        if(v?.CoreWebView2==null) return;
        using var d=new SaveFileDialog { Filter="PDF (*.pdf)|*.pdf",FileName="page.pdf",AddExtension=true,OverwritePrompt=true };
        if(d.ShowDialog(this)!=DialogResult.OK) return;
        try { status.Text=await v.CoreWebView2.PrintToPdfAsync(d.FileName)?"PDF ذخیره شد":"ساخت PDF ناموفق بود"; }
        catch { status.Text="ساخت PDF ناموفق بود."; }
    }
    void OpenFullEdge()
    {
        var url=Current?.Source?.ToString();
        if(!SafeUrl(url)) return;
        if(MessageBox.Show(this,"سایت در مرورگر مستقل Edge باز می‌شود؛ نشست آن خارج از مدیریت کافی‌نت است. ادامه؟","Microsoft Edge",MessageBoxButtons.YesNo)==DialogResult.Yes)
        {
            var candidates=new[]{Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86),Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData)};
            var exe=candidates.Select(p=>Path.Combine(p,"Microsoft","Edge","Application","msedge.exe")).FirstOrDefault(File.Exists);
            if(exe==null) { status.Text="Microsoft Edge نصب نیست."; return; }
            var info=new ProcessStartInfo(exe){UseShellExecute=false};
            info.ArgumentList.Add("--inprivate"); info.ArgumentList.Add(url!);
            Process.Start(info);
        }
    }
    async Task Smoke()
    {
        // Loopback HTTP verifies actual navigation and live tab reuse without a public site.
        using var listener=new System.Net.Sockets.TcpListener(System.Net.IPAddress.Loopback,0);
        listener.Start();
        var port=((System.Net.IPEndPoint)listener.LocalEndpoint).Port;
        var url=$"http://127.0.0.1:{port}/";
        var hits=0;
        using var cancel=new CancellationTokenSource(TimeSpan.FromSeconds(35));
        var server=Task.Run(async()=>{
            while(!cancel.IsCancellationRequested)
            {
                try
                {
                    using var client=await listener.AcceptTcpClientAsync(cancel.Token);
                    using var stream=client.GetStream();
                    using var reader=new StreamReader(stream,Encoding.ASCII,leaveOpen:true);
                    var line=await reader.ReadLineAsync(cancel.Token);
                    if(line==null) continue;
                    while(!string.IsNullOrEmpty(await reader.ReadLineAsync(cancel.Token))) { }
                    if(line.StartsWith("GET / HTTP/")) Interlocked.Increment(ref hits);
                    var html="<html><head><title>Javan Edge smoke</title></head><body><input id='draft' value='initial'></body></html>";
                    var bytes=Encoding.UTF8.GetBytes(html);
                    var header=Encoding.ASCII.GetBytes($"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: {bytes.Length}\r\nConnection: close\r\n\r\n");
                    await stream.WriteAsync(header,cancel.Token); await stream.WriteAsync(bytes,cancel.Token);
                }
                catch(OperationCanceledException) { break; }
                catch(IOException) { }
                catch(System.Net.Sockets.SocketException) { break; }
            }
        });
        try
        {
            var v=await OpenAsync("test",url,"test")??throw new Exception("No view");
            for(int i=0;i<120 && v.CoreWebView2.DocumentTitle!="Javan Edge smoke";i++) await Task.Delay(200);
            if(v.CoreWebView2.DocumentTitle!="Javan Edge smoke") throw new Exception("HTTP navigation failed");
            await v.CoreWebView2.ExecuteScriptAsync("document.getElementById('draft').value='preserved'");
            var again=await OpenAsync("test",url,"test");
            var value=await again!.CoreWebView2.ExecuteScriptAsync("document.getElementById('draft').value");
            if(!ReferenceEquals(v,again) || value!="\"preserved\"" || tabs.TabCount!=1 || hits!=1) throw new Exception("Tab reuse failed");
            Emit("pass","WebView2 HTTP navigation and live tab reuse verified; requests="+hits);
            Result=0;
        }
        catch(Exception ex) { Emit("failure",ex.Message); Result=1; }
        finally { cancel.Cancel(); listener.Stop(); Close(); }
    }
}
