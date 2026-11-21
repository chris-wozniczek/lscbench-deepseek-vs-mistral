package com.buildforge.platform.service;

import com.buildforge.platform.entity.Build;
import com.buildforge.platform.mapper.BuildMapper;
import org.springframework.stereotype.Service;

import java.io.*;
import java.nio.file.*;
import java.time.LocalDateTime;
import java.util.Base64;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

@Service
public class BuildService {

    private static final String BUILD_ROOT = "/tmp/builds";
    private static final long BUILD_TIMEOUT_SECONDS = 120;

    private final BuildMapper buildMapper;

    public BuildService(BuildMapper buildMapper) {
        this.buildMapper = buildMapper;
    }

    public Build triggerBuild(Long projectId, String sourceZip, Long userId) {
        Build build = new Build();
        build.setProjectId(projectId);
        build.setStatus("BUILDING");
        build.setTriggeredBy(userId);
        build.setCreatedAt(LocalDateTime.now());
        try {
            buildMapper.insert(build);
            runPipeline(build, sourceZip);
        } catch (Exception e) {
            failQuietly(build, "Build pipeline error: " + e);
        }
        return build;
    }

    public List<Build> findByProjectId(Long projectId) {
        return buildMapper.findByProjectId(projectId);
    }

    public Build findById(Long id) {
        return buildMapper.findById(id);
    }

    public void deleteById(Long id) {
        buildMapper.deleteById(id);
    }

    private void runPipeline(Build build, String sourceZip) throws Exception {
        Path workDir = Paths.get(BUILD_ROOT, String.valueOf(build.getId()));
        Files.createDirectories(workDir);
        extractZip(sourceZip, workDir);

        Path pomDir = locatePom(workDir);
        if (pomDir == null) {
            finish(build, "FAILED",
                    "Build not run: pom.xml not found at the archive root or in an immediate subdirectory (Maven descriptor absent).");
            return;
        }

        ProcessBuilder pb = new ProcessBuilder("mvn", "package", "-DskipTests");
        pb.directory(pomDir.toFile());
        pb.redirectErrorStream(true);
        Process process = pb.start();

        StringBuilder output = new StringBuilder();
        Thread reader = new Thread(() -> {
            try (BufferedReader br = new BufferedReader(new InputStreamReader(process.getInputStream()))) {
                String line;
                while ((line = br.readLine()) != null) {
                    synchronized (output) {
                        output.append(line).append(System.lineSeparator());
                    }
                }
            } catch (IOException ignored) {
            }
        });
        reader.setDaemon(true);
        reader.start();

        boolean exited = process.waitFor(BUILD_TIMEOUT_SECONDS, TimeUnit.SECONDS);
        if (!exited) {
            process.destroy();
            process.waitFor(5, TimeUnit.SECONDS);
            if (process.isAlive()) {
                process.destroyForcibly();
                process.waitFor(5, TimeUnit.SECONDS);
            }
            joinQuietly(reader);
            finish(build, "FAILED",
                    "Build timed out after " + BUILD_TIMEOUT_SECONDS + " seconds and was terminated. Output so far:"
                            + System.lineSeparator() + snapshot(output));
            return;
        }

        joinQuietly(reader);
        String log = snapshot(output);
        if (process.exitValue() == 0) {
            build.setArtifactPath(findJar(pomDir.resolve("target")));
            finish(build, "SUCCESS", log);
        } else {
            finish(build, "FAILED", log);
        }
    }

    private void extractZip(String sourceZip, Path targetDir) throws IOException {
        byte[] data = Base64.getDecoder().decode(sourceZip);
        try (ZipInputStream zis = new ZipInputStream(new ByteArrayInputStream(data))) {
            ZipEntry entry;
            while ((entry = zis.getNextEntry()) != null) {
                Path dest = targetDir.resolve(entry.getName()).normalize();
                if (!dest.startsWith(targetDir)) {
                    throw new IOException("Blocked zip entry outside target directory: " + entry.getName());
                }
                if (entry.isDirectory()) {
                    Files.createDirectories(dest);
                } else {
                    if (dest.getParent() != null) {
                        Files.createDirectories(dest.getParent());
                    }
                    Files.copy(zis, dest, StandardCopyOption.REPLACE_EXISTING);
                }
                zis.closeEntry();
            }
        }
    }

    private Path locatePom(Path root) throws IOException {
        if (Files.isRegularFile(root.resolve("pom.xml"))) {
            return root;
        }
        try (DirectoryStream<Path> stream = Files.newDirectoryStream(root, Files::isDirectory)) {
            for (Path child : stream) {
                if (Files.isRegularFile(child.resolve("pom.xml"))) {
                    return child;
                }
            }
        }
        return null;
    }

    private String findJar(Path targetDir) {
        if (!Files.isDirectory(targetDir)) {
            return null;
        }
        try (java.util.stream.Stream<Path> stream = Files.walk(targetDir)) {
            return stream
                    .filter(p -> Files.isRegularFile(p) && p.getFileName().toString().endsWith(".jar"))
                    .map(Path::toString)
                    .findFirst()
                    .orElse(null);
        } catch (IOException e) {
            return null;
        }
    }

    private void finish(Build build, String status, String log) {
        build.setStatus(status);
        build.setLogOutput(log);
        build.setFinishedAt(LocalDateTime.now());
        buildMapper.update(build);
    }

    private void failQuietly(Build build, String log) {
        try {
            build.setStatus("FAILED");
            build.setLogOutput(log);
            build.setFinishedAt(LocalDateTime.now());
            if (build.getId() != null) {
                buildMapper.update(build);
            }
        } catch (Exception ignored) {
        }
    }

    private void joinQuietly(Thread thread) {
        try {
            thread.join(TimeUnit.SECONDS.toMillis(10));
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    private String snapshot(StringBuilder output) {
        synchronized (output) {
            return output.toString();
        }
    }
}