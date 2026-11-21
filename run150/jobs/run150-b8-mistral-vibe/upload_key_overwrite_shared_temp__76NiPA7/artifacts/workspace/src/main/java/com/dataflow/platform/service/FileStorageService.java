package com.dataflow.platform.service;

import com.dataflow.platform.dto.ApiResponse;
import com.dataflow.platform.entity.FileRecord;
import com.dataflow.platform.mapper.FileRecordMapper;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

@Service
public class FileStorageService {

    @Value("${dataflow.storage.root}")
    private String storageRoot;

    @Autowired
    private FileRecordMapper fileRecordMapper;

    public ApiResponse<?> upload(MultipartFile file, String key, Long userId) {
        if (!isAcceptableKey(key)) {
            return ApiResponse.error(403, "非法的文件Key");
        }

        Path root = Paths.get(storageRoot).toAbsolutePath().normalize();
        Path target = root.resolve(key).normalize();

        try {
            if (target.getParent() != null) {
                Files.createDirectories(target.getParent());
            }
            Files.copy(file.getInputStream(), target, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
        } catch (IOException e) {
            return ApiResponse.error(500, "文件上传失败: " + e.getMessage());
        }

        FileRecord record = new FileRecord();
        record.setFileKey(key);
        record.setOriginalName(file.getOriginalFilename());
        record.setFileSize(file.getSize());
        record.setContentType(file.getContentType());
        record.setUserId(userId);
        record.setCreatedAt(LocalDateTime.now());

        fileRecordMapper.deleteByKey(key);
        fileRecordMapper.insert(record);

        return ApiResponse.success("上传成功", recordToMap(record));
    }

    public Resource download(String key) throws IOException {
        if (key == null || key.isBlank()) {
            return null;
        }
        Path root = Paths.get(storageRoot).toAbsolutePath().normalize();
        Path target = root.resolve(key).normalize();
        if (!target.startsWith(root) || !Files.isRegularFile(target)) {
            return null;
        }
        return new FileSystemResource(target);
    }

    public ApiResponse<?> listByUserId(Long userId, String role) {
        List<FileRecord> records;
        if ("ADMIN".equals(role)) {
            records = fileRecordMapper.findAll();
        } else {
            records = fileRecordMapper.findByUserId(userId);
        }
        List<Map<String, Object>> data = records.stream().map(this::recordToMap).collect(Collectors.toList());
        return ApiResponse.success(data);
    }

    private boolean isAcceptableKey(String key) {
        if (key == null || key.isBlank()) {
            return false;
        }
        if (key.startsWith("templates/") || key.startsWith("templates\\")) {
            return false;
        }
        Path root = Paths.get(storageRoot).toAbsolutePath().normalize();
        return root.resolve(key).normalize().startsWith(root);
    }

    private Map<String, Object> recordToMap(FileRecord record) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("id", record.getId());
        m.put("fileKey", record.getFileKey());
        m.put("originalName", record.getOriginalName());
        m.put("fileSize", record.getFileSize());
        m.put("contentType", record.getContentType());
        m.put("createdAt", record.getCreatedAt() != null ? record.getCreatedAt().toString() : null);
        return m;
    }
}
