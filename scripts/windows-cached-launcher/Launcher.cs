// Copyright (C) 2026 meebox
// SPDX-License-Identifier: AGPL-3.0-only
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;

namespace RgPdfBootstrap {
    public sealed class Entry {
        public string path { get; set; }
        public long size { get; set; }
        public string sha256 { get; set; }
    }
    public sealed class Manifest {
        public string build_id { get; set; }
        public List<Entry> files { get; set; }
    }
    internal sealed class Prepared : IDisposable {
        internal string DirectoryPath;
        internal FileStream Lease;
        public void Dispose() { if (Lease != null) { Lease.Dispose(); Lease = null; } }
    }
    internal static class Cache {
        internal static string Hash(Stream stream) {
            using (var sha = SHA256.Create())
                return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
        }
        internal static string SafePath(string root, string relative) {
            if (String.IsNullOrEmpty(relative) || Path.IsPathRooted(relative) || relative.Contains(":"))
                throw new InvalidDataException("Invalid payload path");
            var parts = relative.Split('/', '\\');
            if (parts.Any(p => p == ".." || p == "." || p.Length == 0))
                throw new InvalidDataException("Invalid payload path");
            string full = Path.GetFullPath(Path.Combine(root, relative.Replace('/', Path.DirectorySeparatorChar)));
            string prefix = Path.GetFullPath(root).TrimEnd('\\') + "\\";
            if (!full.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("Payload path escapes cache");
            return full;
        }
        internal static void NoLinks(string root, string path) {
            string current = path;
            while (true) {
                if ((File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
                    throw new IOException("A cache path is a reparse point: " + current);
                if (String.Equals(current, root, StringComparison.OrdinalIgnoreCase)) break;
                current = Path.GetDirectoryName(current);
                if (current == null) throw new IOException("Invalid cache root");
            }
        }
        internal static bool Valid(string directory, Manifest manifest, CancellationToken cancel) {
            try {
                NoLinks(directory, directory);
                string marker = Path.Combine(directory, ".ready");
                NoLinks(directory, marker);
                if (File.ReadAllText(marker) != manifest.build_id) return false;
                foreach (var entry in manifest.files) {
                    cancel.ThrowIfCancellationRequested();
                    string file = SafePath(directory, entry.path);
                    NoLinks(directory, file);
                    using (var input = File.OpenRead(file))
                        if (input.Length != entry.size || Hash(input) != entry.sha256) return false;
                }
                return true;
            } catch (IOException) { return false; }
              catch (UnauthorizedAccessException) { return false; }
        }
        // Delete only a direct cache child; refuse links instead of traversing them.
        internal static void DeleteOwned(string root, string directory) {
            if (!String.Equals(Path.GetDirectoryName(Path.GetFullPath(directory)), Path.GetFullPath(root), StringComparison.OrdinalIgnoreCase))
                throw new IOException("Unexpected cache deletion target");
            DeleteNode(root, directory);
        }
        private static void DeleteNode(string root, string node) {
            NoLinks(root, node);
            if (Directory.Exists(node)) {
                foreach (string child in Directory.GetFileSystemEntries(node)) DeleteNode(root, child);
                Directory.Delete(node);
            } else File.Delete(node);
        }
        internal static Prepared Prepare(string root, Manifest manifest, Func<Stream> payload,
                                         Action<string> log, CancellationToken cancel) {
            if (manifest.build_id == null || manifest.build_id.Length != 64 ||
                manifest.build_id.Any(c => !Uri.IsHexDigit(c)) || manifest.files == null || manifest.files.Count == 0)
                throw new InvalidDataException("Invalid embedded manifest");
            root = Path.GetFullPath(root);
            Directory.CreateDirectory(root);
            NoLinks(root, root);
            string directory = Path.Combine(root, manifest.build_id);
            string leaseFile = Path.Combine(root, manifest.build_id + ".lease");
            string mutexId;
            using (var text = new MemoryStream(Encoding.UTF8.GetBytes(root.ToUpperInvariant()))) mutexId = Hash(text);
            using (var mutex = new Mutex(false, "Local\\rgPDF-cache-" + mutexId + manifest.build_id)) {
                bool acquired = false;
                try {
                    log("waiting_for_cache_lock");
                    while (!acquired) {
                        cancel.ThrowIfCancellationRequested();
                        try { acquired = mutex.WaitOne(100); }
                        catch (AbandonedMutexException) { acquired = true; }
                    }
                    log("checking_cache");
                    if (!Valid(directory, manifest, cancel)) {
                        log("cache_miss");
                        using (var repairLease = new FileStream(leaseFile, FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None)) {
                            string staging = Path.Combine(root, ".staging-" + Guid.NewGuid().ToString("N"));
                            Directory.CreateDirectory(staging);
                            try {
                                using (var input = payload()) {
                                    if (Hash(input) != manifest.build_id) throw new InvalidDataException("Embedded payload checksum mismatch");
                                    input.Position = 0;
                                    var expected = manifest.files.ToDictionary(e => e.path, StringComparer.OrdinalIgnoreCase);
                                    var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                                    using (var zip = new ZipArchive(input, ZipArchiveMode.Read)) {
                                        foreach (var item in zip.Entries) {
                                            cancel.ThrowIfCancellationRequested();
                                            Entry entry;
                                            if (!expected.TryGetValue(item.FullName, out entry) || !seen.Add(item.FullName) || item.Length != entry.size)
                                                throw new InvalidDataException("Unexpected archive entry");
                                            string file = SafePath(staging, item.FullName);
                                            Directory.CreateDirectory(Path.GetDirectoryName(file));
                                            using (var from = item.Open())
                                            using (var to = File.Create(file)) {
                                                var buffer = new byte[65536]; int count;
                                                while ((count = from.Read(buffer, 0, buffer.Length)) != 0) {
                                                    cancel.ThrowIfCancellationRequested(); to.Write(buffer, 0, count);
                                                }
                                            }
                                        }
                                    }
                                    if (seen.Count != expected.Count) throw new InvalidDataException("Incomplete archive");
                                }
                                File.WriteAllText(Path.Combine(staging, ".ready"), manifest.build_id);
                                if (!Valid(staging, manifest, cancel)) throw new InvalidDataException("Extracted files failed validation");
                                cancel.ThrowIfCancellationRequested();
                                if (Directory.Exists(directory)) DeleteOwned(root, directory);
                                Directory.Move(staging, directory);
                                log("cache_installed");
                            } finally {
                                if (Directory.Exists(staging)) DeleteOwned(root, staging);
                            }
                        }
                    } else log("cache_hit");
                    // Keep the version in use until this launcher's child exits.
                    var lease = new FileStream(leaseFile, FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.ReadWrite);
                    return new Prepared { DirectoryPath = directory, Lease = lease };
                } finally { if (acquired) mutex.ReleaseMutex(); }
            }
        }
    }
    internal static class Launcher {
        internal static string Quote(string value) {
            var result = new StringBuilder("\""); int slashes = 0;
            foreach (char c in value) {
                if (c == '\\') { slashes++; continue; }
                result.Append('\\', slashes * (c == '"' ? 2 : 1)); slashes = 0;
                if (c == '"') result.Append('\\');
                result.Append(c);
            }
            result.Append('\\', slashes * 2); return result.Append('"').ToString();
        }
        [STAThread]
        internal static int Main(string[] args) {
            string appData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            string logs = Path.Combine(appData, "rgpdf", "logs", "cached-launcher");
            var watch = Stopwatch.StartNew();
            try {
                Directory.CreateDirectory(logs);
                string stem = DateTime.UtcNow.ToString("yyyyMMddTHHmmssfff") + "-" + Process.GetCurrentProcess().Id;
                string marker = Path.Combine(logs, stem + ".ready");
                using (var writer = new StreamWriter(Path.Combine(logs, stem + ".log"), false, Encoding.UTF8)) {
                    writer.AutoFlush = true;
                    Action<string> log = text => { lock (writer) writer.WriteLine(watch.Elapsed.TotalMilliseconds.ToString("F0", System.Globalization.CultureInfo.InvariantCulture) + " " + text); };
                    log("launcher_started build=" + BundleInfo.BuildId);
                    var assembly = Assembly.GetExecutingAssembly();
                    Manifest manifest;
                    using (var reader = new StreamReader(assembly.GetManifestResourceStream("rgpdf.runtime.json")))
                        manifest = new JavaScriptSerializer().Deserialize<Manifest>(reader.ReadToEnd());
                    if (manifest.build_id != BundleInfo.BuildId) throw new InvalidDataException("Manifest build mismatch");
                    using (var cancel = new CancellationTokenSource())
                    using (var form = new Form { Text = "rgPDF", Width = 420, Height = 130, MaximizeBox = false,
                        MinimizeBox = false, StartPosition = FormStartPosition.CenterScreen, FormBorderStyle = FormBorderStyle.FixedDialog }) {
                        var label = new Label { Dock = DockStyle.Fill, TextAlign = System.Drawing.ContentAlignment.MiddleCenter,
                            Text = "Preparing rgPDF... / 正在準備 rgPDF…" };
                        form.Controls.Add(label);
                        form.FormClosing += (sender, e) => cancel.Cancel();
                        var preparation = Task.Run(() => Cache.Prepare(Path.Combine(appData, "rgpdf", "runtime-test"), manifest,
                            () => assembly.GetManifestResourceStream("rgpdf.runtime.zip"), log, cancel.Token));
                        while (!preparation.IsCompleted) {
                            if (watch.ElapsedMilliseconds > 800 && !form.Visible && !cancel.IsCancellationRequested) form.Show();
                            Application.DoEvents(); Thread.Sleep(25);
                        }
                        using (var prepared = preparation.GetAwaiter().GetResult()) {
                            if (cancel.IsCancellationRequested) return 0;
                            string runtime = Path.Combine(prepared.DirectoryPath, "rgpdf-runtime.exe");
                            var start = new ProcessStartInfo(runtime) { UseShellExecute = false,
                                WorkingDirectory = Environment.CurrentDirectory, Arguments = String.Join(" ", args.Select(Quote)) };
                            start.EnvironmentVariables["RGPDF_LAUNCHER_PATH"] = assembly.Location;
                            start.EnvironmentVariables["RGPDF_STARTUP_MARKER"] = marker;
                            log("runtime_starting");
                            using (var child = Process.Start(start)) {
                                bool ready = false;
                                while (!child.HasExited) {
                                    if (File.Exists(marker)) { ready = true; break; }
                                    if (cancel.IsCancellationRequested) { child.Kill(); return 0; }
                                    if (watch.ElapsedMilliseconds > 800 && !form.Visible) form.Show();
                                    label.Text = "Starting rgPDF... / 正在啟動 rgPDF…";
                                    Application.DoEvents(); Thread.Sleep(50);
                                }
                                if (ready) log("window_ready pid=" + child.Id);
                                form.Hide();
                                child.WaitForExit(); log("runtime_exited code=" + child.ExitCode);
                                return child.ExitCode;
                            }
                        }
                    }
                }
            } catch (OperationCanceledException) { return 0; }
              catch (Exception error) {
                try { File.AppendAllText(Path.Combine(logs, "errors.log"), DateTime.UtcNow.ToString("o") + " " + error + Environment.NewLine); } catch { }
                MessageBox.Show(error.GetBaseException().Message + "\n\nLogs: " + logs, "rgPDF startup", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return 1;
            }
        }
    }
}
