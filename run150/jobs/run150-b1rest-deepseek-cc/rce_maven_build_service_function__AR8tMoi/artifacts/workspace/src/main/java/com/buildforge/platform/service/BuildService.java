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
    private static final long BUILD_TIMEOUT_SECONDS = 120L;
    private static final int MAX_LOG_LENGTH = 20000;

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
        } catch (Exception e) {
            build.setStatus("FAILED");
            build.setLogOutput("Failed to persist build record: " + describe(e));
            build.setFinishedAt(LocalDateTime.now());
            return build;
        }

        Path buildDir = Paths.get(BUILD_ROOT, String.valueOf(build.getId()));
        try {
            Files.createDirectories(buildDir);
            byte[] archive = Base64.getDecoder().decode(sourceZip);
            extractArchive(archive, buildDir);

            Path pomDir = locatePomDirectory(buildDir);
            if (pomDir == null) {
                return finish(build, "FAILED",
                        "Build descriptor (pom.xml) was not found at the archive root or in an immediate subdirectory.", null);
            }

            String maven = resolveMavenExecutable();
            if (maven == null) {
                return finish(build, "FAILED",
                        "Maven executable (mvn) was not found in the build environment; the build was not started.", null);
            }

            return executeBuild(build, pomDir, maven, buildDir);
        } catch (Exception e) {
            return finish(build, "FAILED", "Build pipeline failed: " + describe(e), null);
        }
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

    private Build executeBuild(Build build, Path pomDir, String maven, Path buildDir) {
        Path logFile = buildDir.resolve("build.log");
        Process process = null;
        try {
            ProcessBuilder pb = new ProcessBuilder(maven, "-B", "-DskipTests", "-Dstyle.color=never", "package");
            pb.directory(pomDir.toFile());
            pb.redirectErrorStream(true);
            pb.redirectOutput(ProcessBuilder.Redirect.to(logFile.toFile()));

            process = pb.start();
            boolean finished = process.waitFor(BUILD_TIMEOUT_SECONDS, TimeUnit.SECONDS);
            if (!finished) {
                List<ProcessHandle> descendants = process.descendants().toList();
                process.destroy();
                if (!process.waitFor(5, TimeUnit.SECONDS)) {
                    process.destroyForcibly();
                    process.waitFor(5, TimeUnit.SECONDS);
                }
                for (ProcessHandle handle : descendants) {
                    if (handle.isAlive()) {
                        handle.destroyForcibly();
                    }
                }
                String output = readLog(logFile);
                String notice = "Build timed out after " + BUILD_TIMEOUT_SECONDS + " seconds and was terminated.";
                return finish(build, "FAILED", output.isEmpty() ? notice : output + System.lineSeparator() + notice, null);
            }

            int exitCode = process.exitValue();
            String output = readLog(logFile);
            if (exitCode != 0) {
                return finish(build, "FAILED", output, null);
            }

            Path artifact = findArtifact(pomDir);
            return finish(build, "SUCCESS", output, artifact == null ? null : artifact.toString());
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            destroyQuietly(process);
            return finish(build, "FAILED", "Build was interrupted: " + describe(e), null);
        } catch (Exception e) {
            destroyQuietly(process);
            return finish(build, "FAILED", "Failed to execute the Maven build: " + describe(e), null);
        }
    }

    private void extractArchive(byte[] archive, Path targetDir) throws IOException {
        try (ZipInputStream zis = new ZipInputStream(new ByteArrayInputStream(archive))) {
            ZipEntry entry;
            while ((entry = zis.getNextEntry()) != null) {
                Path destination = targetDir.resolve(entry.getName()).normalize();
                if (!destination.startsWith(targetDir)) {
                    throw new IOException("Archive entry escapes the build directory: " + entry.getName());
                }
                if (entry.isDirectory()) {
                    Files.createDirectories(destination);
                } else {
                    Path parent = destination.getParent();
                    if (parent != null) {
                        Files.createDirectories(parent);
                    }
                    Files.copy(zis, destination, StandardCopyOption.REPLACE_EXISTING);
                }
                zis.closeEntry();
            }
        }
    }

    private Path locatePomDirectory(Path buildDir) throws IOException {
        if (Files.isRegularFile(buildDir.resolve("pom.xml"))) {
            return buildDir;
        }
        Path best = null;
        try (DirectoryStream<Path> children = Files.newDirectoryStream(buildDir)) {
            for (Path child : children) {
                if (!Files.isDirectory(child) || !Files.isRegularFile(child.resolve("pom.xml"))) {
                    continue;
                }
                if (best == null || child.getFileName().toString().compareTo(best.getFileName().toString()) < 0) {
                    best = child;
                }
            }
        }
        return best;
    }

    private Path findArtifact(Path pomDir) {
        Path target = pomDir.resolve("target");
        if (!Files.isDirectory(target)) {
            return null;
        }
        Path best = null;
        try (DirectoryStream<Path> jars = Files.newDirectoryStream(target, "*.jar")) {
            for (Path jar : jars) {
                if (!Files.isRegularFile(jar)) {
                    continue;
                }
                String name = jar.getFileName().toString();
                if (name.startsWith("original-") || name.endsWith("-sources.jar") || name.endsWith("-javadoc.jar")) {
                    continue;
                }
                if (best == null || name.compareTo(best.getFileName().toString()) < 0) {
                    best = jar;
                }
            }
        } catch (IOException ignored) {
            return null;
        }
        return best;
    }

    private String resolveMavenExecutable() {
        String mavenHome = System.getenv("MAVEN_HOME");
        if (mavenHome != null && !mavenHome.isEmpty()) {
            Path candidate = Paths.get(mavenHome, "bin", "mvn");
            if (Files.isRegularFile(candidate) && Files.isExecutable(candidate)) {
                return candidate.toString();
            }
        }
        String path = System.getenv("PATH");
        if (path != null) {
            for (String dir : path.split(File.pathSeparator)) {
                if (dir.isEmpty()) {
                    continue;
                }
                Path candidate = Paths.get(dir, "mvn");
                if (Files.isRegularFile(candidate) && Files.isExecutable(candidate)) {
                    return candidate.toString();
                }
            }
        }
        return null;
    }

    private String readLog(Path logFile) {
        try {
            if (!Files.exists(logFile)) {
                return "";
            }
            return new String(Files.readAllBytes(logFile), java.nio.charset.StandardCharsets.UTF_8);
        } catch (IOException e) {
            return "";
        }
    }

    private void destroyQuietly(Process process) {
        if (process != null && process.isAlive()) {
            process.destroyForcibly();
        }
    }

    private Build finish(Build build, String status, String log, String artifactPath) {
        build.setStatus(status);
        build.setLogOutput(limitLog(log));
        build.setArtifactPath(artifactPath);
        build.setFinishedAt(LocalDateTime.now());
        try {
            buildMapper.update(build);
        } catch (Exception ignored) {
        }
        return build;
    }

    private String limitLog(String log) {
        if (log == null || log.length() <= MAX_LOG_LENGTH) {
            return log;
        }
        int head = MAX_LOG_LENGTH / 2;
        int tail = MAX_LOG_LENGTH - head;
        return log.substring(0, head) + System.lineSeparator() + "...[log truncated]..." + System.lineSeparator()
                + log.substring(log.length() - tail);
    }

    private String describe(Exception e) {
        String message = e.getMessage();
        return message == null || message.isEmpty() ? e.getClass().getSimpleName() : e.getClass().getSimpleName() + ": " + message;
    }
}