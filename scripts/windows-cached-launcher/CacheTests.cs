// Copyright (C) 2026 meebox
// SPDX-License-Identifier: AGPL-3.0-only
using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace RgPdfBootstrap {
    internal static class CacheTests {
        [DllImport("shell32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        static extern IntPtr CommandLineToArgvW(string command, out int count);
        [DllImport("kernel32.dll")]
        static extern IntPtr LocalFree(IntPtr value);
        static void Assert(bool ok, string message) { if (!ok) throw new Exception(message); }
        static Tuple<Manifest, byte[]> Payload(string content) {
            byte[] value = Encoding.UTF8.GetBytes(content);
            byte[] archive;
            using (var memory = new MemoryStream()) {
                using (var zip = new ZipArchive(memory, ZipArchiveMode.Create, true))
                    using (var stream = zip.CreateEntry("rgpdf-runtime.exe").Open()) stream.Write(value, 0, value.Length);
                archive = memory.ToArray();
            }
            string hash, id;
            using (var stream = new MemoryStream(value)) hash = Cache.Hash(stream);
            using (var stream = new MemoryStream(archive)) id = Cache.Hash(stream);
            return Tuple.Create(new Manifest { build_id = id, files = new List<Entry> {
                new Entry { path = "rgpdf-runtime.exe", size = value.Length, sha256 = hash }
            } }, archive);
        }
        static int Main() {
            string root = Path.Combine(Path.GetTempPath(), "rgpdf-native-cache-test-" + Guid.NewGuid().ToString("N"));
            var data = Payload("original");
            int opened = 0;
            Func<Stream> stream = () => { Interlocked.Increment(ref opened); return new MemoryStream(data.Item2); };
            Action<string> log = text => Console.WriteLine(text);
            try {
                string directory;
                using (var first = Cache.Prepare(root, data.Item1, stream, log, CancellationToken.None)) directory = first.DirectoryPath;
                Assert(opened == 1, "Cold prepare must extract once");
                DateTime written = File.GetLastWriteTimeUtc(Path.Combine(directory, "rgpdf-runtime.exe"));
                using (var warm = Cache.Prepare(root, data.Item1, stream, log, CancellationToken.None)) {
                    Assert(opened == 1, "Warm prepare must not read the payload");
                    Assert(File.GetLastWriteTimeUtc(Path.Combine(directory, "rgpdf-runtime.exe")) == written, "Warm prepare rewrote cache");
                    File.WriteAllText(Path.Combine(directory, "rgpdf-runtime.exe"), "modified");
                    bool blocked = false;
                    try { using (var other = Cache.Prepare(root, data.Item1, stream, log, CancellationToken.None)) {} }
                    catch (IOException) { blocked = true; }
                    Assert(blocked, "In-use corrupt runtime must not be replaced");
                }
                using (var repaired = Cache.Prepare(root, data.Item1, stream, log, CancellationToken.None))
                    Assert(File.ReadAllText(Path.Combine(directory, "rgpdf-runtime.exe")) == "original", "Same-size corruption not repaired");
                File.Delete(Path.Combine(directory, ".ready"));
                using (var repaired = Cache.Prepare(root, data.Item1, stream, log, CancellationToken.None)) {}
                File.Delete(Path.Combine(directory, "rgpdf-runtime.exe"));
                using (var repaired = Cache.Prepare(root, data.Item1, stream, log, CancellationToken.None)) {}
                Assert(opened == 4, "Expected three repairs plus cold extraction");
                var newer = Payload("new build");
                using (var running = Cache.Prepare(root, data.Item1, stream, log, CancellationToken.None))
                using (var upgraded = Cache.Prepare(root, newer.Item1, () => new MemoryStream(newer.Item2), log, CancellationToken.None)) {
                    Assert(upgraded.DirectoryPath != running.DirectoryPath && Directory.Exists(running.DirectoryPath), "Upgrade changed running build");
                }
                foreach (string unsafePath in new[] { "../outside", "C:/absolute", "folder/../outside", "file:stream" }) {
                    bool blocked = false;
                    try { Cache.SafePath(root, unsafePath); } catch (InvalidDataException) { blocked = true; }
                    Assert(blocked, "Unsafe archive path allowed");
                }
                var concurrent = Payload("concurrent"); int reads = 0;
                Action prepare = () => {
                    using (var ready = Cache.Prepare(root, concurrent.Item1,
                        () => { Interlocked.Increment(ref reads); Thread.Sleep(100); return new MemoryStream(concurrent.Item2); }, log, CancellationToken.None)) Thread.Sleep(100);
                };
                Task.WaitAll(Task.Run(prepare), Task.Run(prepare));
                Assert(reads == 1, "Concurrent launch extracted more than once");
                string[] arguments = { "", "hello", "a b", "C:\\", "quote\"here", "中文" };
                foreach (string arg in arguments) {
                    int count;
                    IntPtr argv = CommandLineToArgvW("program.exe " + Launcher.Quote(arg), out count);
                    try {
                        Assert(count == 2 && Marshal.PtrToStringUni(Marshal.ReadIntPtr(argv, IntPtr.Size)) == arg, "Argument round-trip failed");
                    } finally { LocalFree(argv); }
                }
                Console.WriteLine("Native cache tests passed: cold/warm, repair, lease, upgrade, traversal and concurrency");
                return 0;
            } finally {
                // root is generated exclusively for this harness, under TEMP.
                if (Path.GetDirectoryName(Path.GetFullPath(root)).Equals(Path.GetFullPath(Path.GetTempPath()).TrimEnd('\\'), StringComparison.OrdinalIgnoreCase))
                    foreach (string child in Directory.GetFileSystemEntries(root)) {
                        if (Directory.Exists(child)) Cache.DeleteOwned(root, child); else File.Delete(child);
                    }
                Directory.Delete(root);
            }
        }
    }
}
