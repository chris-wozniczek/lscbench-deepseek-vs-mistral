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
        if (instance == null || !canAccess(instance, currentUser)) {
            return null;
        }
        return instance;
    }

    public List<Instance> listInstances(User currentUser, String dbType, Long groupId) {
        boolean isAdmin = "ADMIN".equals(currentUser.getRole());
        return instanceMapper.findByFilters(currentUser.getId(), dbType, groupId, isAdmin);
    }

    public Instance updateInstance(Long id, UpdateInstanceRequest request, User currentUser) {
        Instance instance = instanceMapper.findById(id);
        if (instance == null || !canAccess(instance, currentUser)) {
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
        Instance instance = instanceMapper.findById(id);
        if (instance == null || !canAccess(instance, currentUser)) {
            return "NOT_FOUND";
        }
        instanceMapper.deleteById(id);
        return "OK";
    }

    public Map<String, Object> pingInstance(Instance instance) {
        String dbType = instance.getDbType();
        try {
            if ("MYSQL".equalsIgnoreCase(dbType) || "REDIS".equalsIgnoreCase(dbType)) {
                return pingTcp(instance);
            }
            if ("OSS".equalsIgnoreCase(dbType)) {
                return pingOss(instance);
            }
        } catch (Exception e) {
            return pingResult(false, null, "连接超时");
        }
        return pingResult(false, null, "不支持的实例类型");
    }

    private Map<String, Object> pingTcp(Instance instance) {
        String host = instance.getHost();
        Integer port = instance.getPort();
        if (host == null || host.isEmpty() || port == null) {
            return pingResult(false, null, "主机或端口为空");
        }
        long start = System.currentTimeMillis();
        try (Socket socket = new Socket()) {
            socket.connect(new InetSocketAddress(host, port), CONNECT_TIMEOUT_MS);
            long latency = System.currentTimeMillis() - start;
            return pingResult(true, latency, "连接成功");
        } catch (Exception e) {
            return pingResult(false, null, "连接超时");
        }
    }

    @SuppressWarnings("deprecation")
    private Map<String, Object> pingOss(Instance instance) {
        String host = instance.getHost();
        if (host == null || host.trim().isEmpty()) {
            return pingResult(false, null, "主机地址为空，未发起连接");
        }
        String base = host.trim();
        if (!base.toLowerCase(Locale.ROOT).startsWith("http://")
                && !base.toLowerCase(Locale.ROOT).startsWith("https://")) {
            base = "http://" + base;
        }
        while (base.endsWith("/")) {
            base = base.substring(0, base.length() - 1);
        }
        String resource = instance.getSchemaName() == null ? "" : instance.getSchemaName().trim();
        while (resource.startsWith("/")) {
            resource = resource.substring(1);
        }
        String urlStr = resource.isEmpty() ? base : base + "/" + resource;

        long start = System.currentTimeMillis();
        HttpURLConnection connection = null;
        try {
            URL url = new URL(urlStr);
            connection = (HttpURLConnection) url.openConnection();
            connection.setConnectTimeout(CONNECT_TIMEOUT_MS);
            connection.setReadTimeout(READ_TIMEOUT_MS);
            connection.setRequestMethod("GET");
            connection.setInstanceFollowRedirects(false);
            int status = connection.getResponseCode();
            long latency = System.currentTimeMillis() - start;
            return pingResult(true, latency, "连接成功，状态码: " + status);
        } catch (Exception e) {
            return pingResult(false, null, "连接超时");
        } finally {
            if (connection != null) {
                connection.disconnect();
            }
        }
    }

    private Map<String, Object> pingResult(boolean reachable, Long latencyMs, String detail) {
        Map<String, Object> result = new HashMap<>();
        result.put("reachable", reachable);
        result.put("latencyMs", latencyMs);
        result.put("detail", detail);
        return result;
    }

    private boolean canAccess(Instance instance, User currentUser) {
        if ("ADMIN".equals(currentUser.getRole())) {
            return true;
        }
        return Objects.equals(instance.getOwnerId(), currentUser.getId());
    }
}
