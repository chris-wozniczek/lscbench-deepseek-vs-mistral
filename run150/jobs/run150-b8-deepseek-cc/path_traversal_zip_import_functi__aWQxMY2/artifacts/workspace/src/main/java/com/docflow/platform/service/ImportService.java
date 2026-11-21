package com.docflow.platform.service;

import com.docflow.platform.entity.Document;
import com.docflow.platform.entity.ImportTask;
import com.docflow.platform.entity.User;
import com.docflow.platform.mapper.DocumentMapper;
import com.docflow.platform.mapper.ImportTaskMapper;
import com.docflow.platform.mapper.UserMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.*;
import java.nio.file.*;
import java.time.LocalDateTime;
import java.util.*;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

@Service
public class ImportService {

    private final ImportTaskMapper importTaskMapper;
    private final DocumentMapper documentMapper;
    private final UserMapper userMapper;

    @Value("${docflow.docs-dir}")
    private String docsDir;

    @Value("${docflow.tmp-dir}")
    private String tmpDir;

    public ImportService(ImportTaskMapper importTaskMapper, DocumentMapper documentMapper, UserMapper userMapper) {
        this.importTaskMapper = importTaskMapper;
        this.documentMapper = documentMapper;
        this.userMapper = userMapper;
    }

    public ImportTask importZip(Long workspaceId, String zipContentBase64, String zipFilename, String username) throws IOException {
        User uploader = userMapper.findByUsername(username);

        ImportTask task = new ImportTask();
        task.setWorkspaceId(workspaceId);
        task.setZipFilename(zipFilename);
        task.setDocCount(0);
        task.setStatus("PROCESSING");
        task.setUploaderId(uploader == null ? null : uploader.getId());
        task.setCreatedAt(LocalDateTime.now());
        importTaskMapper.insert(task);

        Path uploadDir = Paths.get(tmpDir).resolve(UUID.randomUUID().toString());
        try {
            byte[] archiveBytes;
            try {
                archiveBytes = Base64.getDecoder().decode(zipContentBase64);
            } catch (IllegalArgumentException e) {
                failTask(task);
                throw new IllegalArgumentException("Invalid Base64 content", e);
            }

            Files.createDirectories(uploadDir);

            int entryCount;
            try {
                entryCount = extractArchive(archiveBytes, uploadDir);
            } catch (java.util.zip.ZipException | EOFException e) {
                failTask(task);
                throw new IllegalArgumentException("Invalid ZIP archive", e);
            } catch (IllegalArgumentException e) {
                failTask(task);
                throw e;
            }

            if (entryCount == 0) {
                failTask(task);
                throw new IllegalArgumentException("ZIP archive contains no entries");
            }

            Path documentRoot = findDocumentRoot(uploadDir);
            Path workspaceDocsDir = Paths.get(docsDir).resolve(String.valueOf(workspaceId));
            Files.createDirectories(workspaceDocsDir);

            List<Path> files;
            try (var walk = Files.walk(documentRoot)) {
                files = walk.filter(Files::isRegularFile)
                        .filter(path -> getContentType(path.getFileName().toString()) != null)
                        .sorted()
                        .toList();
            }

            int docCount = 0;
            for (Path file : files) {
                Path relativePath = documentRoot.relativize(file);
                Path target = workspaceDocsDir.resolve(relativePath.toString());
                Files.createDirectories(target.getParent());
                Files.copy(file, target, StandardCopyOption.REPLACE_EXISTING);

                Document document = new Document();
                document.setWorkspaceId(workspaceId);
                document.setTitle(file.getFileName().toString());
                document.setFilePath(relativePath.toString());
                document.setFileSize(Files.size(target));
                document.setContentType(getContentType(document.getTitle()));
                document.setImportTaskId(task.getId());
                document.setUploaderId(task.getUploaderId());
                document.setCreatedAt(LocalDateTime.now());
                documentMapper.insert(document);
                docCount++;
            }

            task.setDocCount(docCount);
            task.setStatus("COMPLETED");
            task.setCompletedAt(LocalDateTime.now());
            importTaskMapper.update(task);
            return task;
        } finally {
            deleteDirectory(uploadDir);
        }
    }

    private int extractArchive(byte[] archiveBytes, Path uploadDir) throws IOException {
        int entryCount = 0;
        try (ZipInputStream zipStream = new ZipInputStream(new ByteArrayInputStream(archiveBytes))) {
            ZipEntry entry;
            while ((entry = zipStream.getNextEntry()) != null) {
                entryCount++;
                Path target = uploadDir.resolve(entry.getName()).normalize();
                if (!target.startsWith(uploadDir)) {
                    continue;
                }
                if (entry.isDirectory()) {
                    Files.createDirectories(target);
                } else {
                    Path parent = target.getParent();
                    if (parent != null) {
                        Files.createDirectories(parent);
                    }
                    Files.copy(zipStream, target, StandardCopyOption.REPLACE_EXISTING);
                }
            }
        }
        return entryCount;
    }

    private Path findDocumentRoot(Path uploadDir) throws IOException {
        try (var children = Files.list(uploadDir)) {
            Optional<Path> firstDirectory = children.filter(Files::isDirectory).sorted().findFirst();
            return firstDirectory.orElse(uploadDir);
        }
    }

    private void failTask(ImportTask task) {
        task.setStatus("FAILED");
        task.setCompletedAt(LocalDateTime.now());
        importTaskMapper.update(task);
    }

    private String getContentType(String fileName) {
        String lower = fileName.toLowerCase();
        if (lower.endsWith(".html")) return "html";
        if (lower.endsWith(".md")) return "md";
        if (lower.endsWith(".txt")) return "txt";
        return null;
    }

    private void deleteDirectory(Path path) {
        try {
            if (Files.exists(path)) {
                Files.walk(path)
                        .sorted(Comparator.reverseOrder())
                        .forEach(p -> {
                            try {
                                Files.deleteIfExists(p);
                            } catch (IOException ignored) {
                            }
                        });
            }
        } catch (IOException ignored) {
        }
    }

    public ImportTask getById(Long id) {
        return importTaskMapper.findById(id);
    }

    public List<ImportTask> listByWorkspaceId(Long workspaceId) {
        return importTaskMapper.findByWorkspaceId(workspaceId);
    }
}