terraform {
  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 3.0"
    }
  }
}

provider "docker" {}

resource "docker_network" "net_a" {
  name   = "it-infra-lab_net_a"
  driver = "bridge"

  ipam_config {
    subnet  = "10.10.1.0/24"
    gateway = "10.10.1.1"
  }

  labels {
    label = "com.docker.compose.config-hash"
    value = "a61542e9dc032bb916713cb67f2b2e382542a244c71b62df7a04f1d109d8559c"
  }
  labels {
    label = "com.docker.compose.network"
    value = "net_a"
  }
  labels {
    label = "com.docker.compose.project"
    value = "it-infra-lab"
  }
  labels {
    label = "com.docker.compose.version"
    value = "5.3.1"
  }
}

resource "docker_network" "net_b" {
  name   = "it-infra-lab_net_b"
  driver = "bridge"

  ipam_config {
    subnet  = "10.10.2.0/24"
    gateway = "10.10.2.1"
  }

  labels {
    label = "com.docker.compose.config-hash"
    value = "b20e593be10a94805a92cbdd19047334d2a78cdb08003afc9d76b293851bfef2"
  }
  labels {
    label = "com.docker.compose.network"
    value = "net_b"
  }
  labels {
    label = "com.docker.compose.project"
    value = "it-infra-lab"
  }
  labels {
    label = "com.docker.compose.version"
    value = "5.3.1"
  }
}

resource "docker_container" "server_a" {
  name       = "server-a"
  image      = "ubuntu:22.04"
  hostname   = "dc.internal.local"
  privileged = true
  restart    = "unless-stopped"

  network_mode = docker_network.net_a.name

  env = ["PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"]

  command = [
    "bash", "-c",
    "apt-get update && apt-get install -y systemd systemd-sysv openssh-server iproute2 && \n         rm -f /lib/systemd/system/multi-user.target.wants/* /etc/systemd/system/*.wants/* &&\n         exec /lib/systemd/systemd"
  ]

  ports {
    internal = 22
    external = 2222
    ip       = "0.0.0.0"
  }
  ports {
    internal = 22
    external = 2222
    ip       = "::"
  }
  ports {
    internal = 51820
    external = 51820
    protocol = "udp"
    ip       = "0.0.0.0"
  }
  ports {
    internal = 51820
    external = 51820
    protocol = "udp"
    ip       = "::"
  }

  networks_advanced {
    name         = docker_network.net_a.name
    ipv4_address = "10.10.1.10"
  }

  volumes {
    host_path      = "${var.lab_data_root}/server-a"
    container_path = "/root"
  }
}

resource "docker_container" "server_b" {
  name       = "server-b"
  image      = "ubuntu:22.04"
  hostname   = "app.internal.local"
  privileged = true
  restart    = "unless-stopped"

  network_mode = docker_network.net_b.name

  env = ["PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"]

  command = [
    "bash", "-c",
    "apt-get update && apt-get install -y systemd systemd-sysv openssh-server iproute2 &&\n         rm -f /lib/systemd/system/multi-user.target.wants/* /etc/systemd/system/*.wants/* &&\n         exec /lib/systemd/systemd"
  ]

  ports {
    internal = 22
    external = 2223
    ip       = "0.0.0.0"
  }
  ports {
    internal = 22
    external = 2223
    ip       = "::"
  }
  ports {
    internal = 8501
    external = 8501
    ip       = "0.0.0.0"
  }
  ports {
    internal = 8501
    external = 8501
    ip       = "::"
  }

  networks_advanced {
    name         = docker_network.net_b.name
    ipv4_address = "10.10.2.10"
  }

  volumes {
    host_path      = "${var.lab_data_root}/server-b"
    container_path = "/root"
  }
}
