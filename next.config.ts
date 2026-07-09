const nextConfig = {
  allowedDevOrigins: ['192.168.1.100', '127.0.0.1', 'localhost'],
  async headers() {
    return [
      {
        source: "/ar-demo",
        headers: [
          {
            key: "Permissions-Policy",
            value: 'camera=(self "http://localhost:8080" "http://127.0.0.1:8080"), microphone=()',
          },
        ],
      },
      {
        source: "/ar-tryon",
        headers: [
          {
            key: "Permissions-Policy",
            value: "camera=(self), microphone=()",
          },
        ],
      },
    ];
  },
};
export default nextConfig;
