resource "google_compute_network" "dev_vpc" {
  auto_create_subnetworks                   = false
  bgp_always_compare_med                    = false
  bgp_best_path_selection_mode              = "LEGACY"
  delete_bgp_always_compare_med             = false
  delete_default_routes_on_create           = false
  deletion_policy                           = "DELETE"
  description                               = null
  enable_ula_internal_ipv6                  = false
  mtu                                       = 0
  name                                      = "log-analyzer-dev-vpc"
  network_firewall_policy_enforcement_order = "AFTER_CLASSIC_FIREWALL"
  network_profile                           = null
  project                                   = "ai-log-analyzer-511017"
  routing_mode                              = "REGIONAL"
}

resource "google_compute_subnetwork" "dev_subnet" {
  allow_subnet_cidr_routes_overlap = false
  deletion_policy                  = "DELETE"
  description                      = null
  ip_cidr_range                    = "10.42.0.0/24"
  ip_collection                    = null
  ipv6_access_type                 = null
  name                             = "log-analyzer-dev-subnet"
  network                          = "https://www.googleapis.com/compute/v1/projects/ai-log-analyzer-511017/global/networks/log-analyzer-dev-vpc"
  private_ip_google_access         = true
  private_ipv6_google_access       = "DISABLE_GOOGLE_ACCESS"
  project                          = "ai-log-analyzer-511017"
  purpose                          = "PRIVATE"
  region                           = "us-central1"
  reserved_internal_range          = null
  resolve_subnet_mask              = null
  role                             = null
  send_secondary_ip_range_if_empty = null
  stack_type                       = "IPV4_ONLY"
}

resource "google_compute_firewall" "googleapis_allow" {
  deletion_policy    = "DELETE"
  description        = null
  destination_ranges = ["199.36.153.8/30"]
  direction          = "EGRESS"
  disabled           = false
  name               = "log-analyzer-dev-googleapis-allow"
  network            = "https://www.googleapis.com/compute/v1/projects/ai-log-analyzer-511017/global/networks/log-analyzer-dev-vpc"
  priority           = 900
  project            = "ai-log-analyzer-511017"
  source_ranges      = []
  target_tags        = ["log-analyzer-dev"]
  allow {
    ports    = ["443"]
    protocol = "tcp"
  }
}

resource "google_compute_firewall" "egress_deny" {
  deletion_policy    = "DELETE"
  description        = null
  destination_ranges = ["0.0.0.0/0"]
  direction          = "EGRESS"
  disabled           = false
  name               = "log-analyzer-dev-egress-deny"
  network            = "https://www.googleapis.com/compute/v1/projects/ai-log-analyzer-511017/global/networks/log-analyzer-dev-vpc"
  priority           = 1000
  project            = "ai-log-analyzer-511017"
  source_ranges      = []
  target_tags        = ["log-analyzer-dev"]
  deny {
    ports    = []
    protocol = "all"
  }
}

resource "google_compute_route" "googleapis" {
  deletion_policy     = "DELETE"
  description         = null
  dest_range          = "199.36.153.8/30"
  name                = "log-analyzer-dev-googleapis"
  network             = "https://www.googleapis.com/compute/v1/projects/ai-log-analyzer-511017/global/networks/log-analyzer-dev-vpc"
  next_hop_gateway    = "https://www.googleapis.com/compute/v1/projects/ai-log-analyzer-511017/global/gateways/default-internet-gateway"
  next_hop_ilb        = null
  next_hop_instance   = null
  next_hop_vpn_tunnel = null
  priority            = 100
  project             = "ai-log-analyzer-511017"
  tags                = []
}

resource "google_dns_managed_zone" "googleapis" {
  deletion_policy = "DELETE"
  description     = "Private Google APIs for log analyzer"
  dns_name        = "googleapis.com."
  force_destroy   = false
  labels          = {}
  name            = "log-analyzer-dev-googleapis"
  project         = "ai-log-analyzer-511017"
  visibility      = "private"
  cloud_logging_config {
    enable_logging = false
  }
  private_visibility_config {
    networks {
      network_url = "https://compute.googleapis.com/compute/v1/projects/ai-log-analyzer-511017/global/networks/log-analyzer-dev-vpc"
    }
  }
}

resource "google_dns_record_set" "googleapis_cname" {
  deletion_policy = "DELETE"
  managed_zone    = "log-analyzer-dev-googleapis"
  name            = "*.googleapis.com."
  project         = "ai-log-analyzer-511017"
  rrdatas         = ["private.googleapis.com."]
  ttl             = 300
  type            = "CNAME"
}

resource "google_dns_record_set" "googleapis_a" {
  deletion_policy = "DELETE"
  managed_zone    = "log-analyzer-dev-googleapis"
  name            = "private.googleapis.com."
  project         = "ai-log-analyzer-511017"
  rrdatas         = ["199.36.153.8", "199.36.153.9", "199.36.153.10", "199.36.153.11"]
  ttl             = 300
  type            = "A"
}
