VAGRANTFILE_API_VERSION = "2"

Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|
  # Ubuntu 14.04
  config.vm.box = "ubuntu/trusty64"

  # Network
  config.vm.hostname = "vagrant.spkrepo"
  config.vm.network "forwarded_port", guest: 80, host: 8080
  config.vm.network "forwarded_port", guest: 443, host: 8443

  # Share for masterless server
  config.vm.synced_folder "salt/roots/", "/srv/"
  config.vm.synced_folder "./", "/var/www/spkrepo/"

  config.vm.provision :salt do |salt|
    # Configure the minion
    salt.minion_config = "salt/minion"
    
    # Show the output of salt
    salt.verbose = true
    
    # Run the highstate on start
    salt.run_highstate = true
  end
end

