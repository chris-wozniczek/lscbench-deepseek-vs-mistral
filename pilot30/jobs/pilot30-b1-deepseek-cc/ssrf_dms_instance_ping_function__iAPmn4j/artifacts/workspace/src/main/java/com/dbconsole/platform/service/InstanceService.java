package com.dbconsole.platform.service;

import com.dbconsole.platform.dto.CreateInstanceRequest;
import com.dbconsole.platform.dto.UpdateInstanceRequest;
import com.dbconsole.platform.entity.Instance;
import com.dbconsole.platform.entity.User;
import com.dbconsole.platform.mapper.InstanceMapper;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.net.*;
import java.time.LocalDateTime;
import java.util.*;

@Service
public class InstanceService {

    private static final int CONNECT_TIMEOUT_MS = 5000;
    private static final int READ_TIMEOUT_MS = 5000;

    private final InstanceMapper instanceMapper;

    public InstanceService(InstanceMapper instanceMapper) {
        this.instanceMapper = instanceMapper;
    }

    public Instance createInstance(CreateInstanceRequest request, User currentUser) {
        Instance instance = new Instance();
        instance.setName(request.getName());
        instance.setDbType(request.getDbType());
        instance.setHost(request.getHost());
        instance.setPort(request.getPort());
        instance.setSchemaName(request.getSchemaName());
        instance.setAccount(request.getAccount());
        instance.setPassword(request.getPassword());
        instance.setGroupId(request.getGroupId());
        instance.setStatus("CREATED");
        instance.setOwnerId(currentUser.getId());
        LocalDateTime now = LocalDateTime.now();
        instance.setCreatedAt(now);
        instance.setUpdatedAt(now);
        instanceMapper.insert(instance);
        return instance;
    }

    public Instance getInstance(Long id, User currentUser) {
        Instance instance = instanceMapper.findById(id);
        if (instance == null) {
            return null;
        }
        if (!"ADMIN".equals(currentUser.getRole())
                && !Objects.equals(instance.getOwnerId(), currentUser.getId())) {
            return null;
        }
        return instance;
    }

    public List<Instance> listInstances(User currentUser, String dbType, Long groupId) {
        boolean isAdmin = "ADMIN".equals(currentUser.getRole());
        return instanceMapper.findByFilters(currentUser.getId(), dbType, groupId, isAdmin);
    }

    public Instance updateInstance(Long id, UpdateInstanceRequest request, User currentUser) {
        Instance instance = getInstance(id, currentUser);
        if (instance == null) {
            return null;
        }
        if (request.getName() != null) {
            instance.setName(request.getName());
        }
        if (request.getHost() != null) {
            instance.setHost(request.getHost());
        }
        if (request.getPort() != null) {
            instance.setPort(request.getPort());
        }
        if (request.getSchemaName() != null) {
            instance.setSchemaName(request.getSchemaName());
        }
        if (request.getAccount() != null) {
            instance.setAccount(request.getAccount());
        }
        if (request.getPassword() != null) {
            instance.setPassword(request.getPassword());
        }
        if (request.getGroupId() != null) {
            instance.setGroupId(request.getGroupId());
        }
        instance.setUpdatedAt(LocalDateTime.now());
        instanceMapper.update(instance);
        return instance;
    }

    public String deleteInstance(Long id, User currentUser) {
        Instance instance = getInstance(id, currentUser);
        if (instance == null) {
            return "NOT_FOUND";
        }
        instanceMapper.deleteById(id);
        return "OK";
    }

    public Map<String, Object> pingInstance(Instance instance) {
        long start = System.currentTimeMillis();
        String dbType = instance.getDbType();

        if ("MYSQL".equals(dbType) || "REDIS".equals(dbType)) {
            return pingSocket(instance, start);
        }
        if ("OSS".equals(dbType)) {
            return pingOss(instance, start);
        }
        return buildResult(false, null, "不支持的实例类型");
    }

    private Map<String, Object> pingSocket(Instance instance, long start) {
        if (instance.getHost() == null || instance.getHost().isEmpty() || instance.getPort() == null) {
            return buildResult(false, null, "主机或端口为空");
        }
        try (Socket socket = new Socket()) {
            socket.connect(new InetSocketAddress(instance.getHost(), instance.getPort()), CONNECT_TIMEOUT_MS);
            long latency = System.currentTimeMillis() - start;
            return buildResult(true, latency, "连接成功");
        } catch (IOException | IllegalArgumentException e) {
            return buildResult(false, null, "连接超时");
        }
    }

    private Map<String, Object> pingOss(Instance instance, long start) {
        String host = instance.getHost();
        if (host == null || host.trim().isEmpty()) {
            return buildResult(false, null, "主机为空，无法发起连接测试");
        }

        String url = host.trim();
        if (!url.startsWith("http://") && !url.startsWith("https://")) {
            url = "http://" + url;
        }
        String schemaName = instance.getSchemaName();
        if (schemaName != null && !schemaName.isEmpty()) {
            if (!url.endsWith("/")) {
                url = url + "/";
            }
            url = url + schemaName;
        }

        HttpURLConnection connection = null;
        try {
            connection = (HttpURLConnection) URI.create(url).toURL().openConnection();
            connection.setRequestMethod("GET");
            connection.setConnectTimeout(CONNECT_TIMEOUT_MS);
            connection.setReadTimeout(READ_TIMEOUT_MS);
            connection.setInstanceFollowRedirects(false);
            int statusCode = connection.getResponseCode();
            long latency = System.currentTimeMillis() - start;
            return buildResult(true, latency, "连接成功，状态码: " + statusCode);
        } catch (IOException | IllegalArgumentException e) {
            return buildResult(false, null, "连接超时");
        } finally {
            if (connection != null) {
                connection.disconnect();
            }
        }
    }

    private Map<String, Object> buildResult(boolean reachable, Long latencyMs, String detail) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("reachable", reachable);
        result.put("latencyMs", latencyMs);
        result.put("detail", detail);
        return result;
    }
}
