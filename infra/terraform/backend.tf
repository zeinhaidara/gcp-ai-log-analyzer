terraform {
  backend "gcs" {
    bucket = "ai-log-analyzer-511017-tfstate"
    prefix = "dev"
  }
}
